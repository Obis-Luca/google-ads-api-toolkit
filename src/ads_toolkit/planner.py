"""Repeatable paused Search staging and shared asset deduplication."""
from urllib.parse import urlparse


def validate_spec(spec):
    if not isinstance(spec.get("ad_groups", []), list):
        raise ValueError("ad_groups must be a list.")
    names = set()
    for group in spec.get("ad_groups", []):
        name = group["name"]
        if not name or name in names:
            raise ValueError("Ad-group names must be nonempty and unique.")
        names.add(name)
        heads, desc = group["headlines"], group["descriptions"]
        for items, low, high, length in [(heads, 3, 15, 30), (desc, 2, 4, 90)]:
            if not low <= len(items) <= high or len(items) != len(set(items)):
                raise ValueError("Invalid RSA asset count or duplicate text.")
            if not all(isinstance(t, str) and 0 < len(t) <= length for t in items):
                raise ValueError("RSA text exceeds Google's character limits.")
        for key in ("path1", "path2"):
            if len(group.get(key, "")) > 15:
                raise ValueError("Display paths must be at most 15 characters.")
        if group.get("path2") and not group.get("path1"):
            raise ValueError("path2 requires path1.")
        url = group.get("final_url", spec.get("final_url", ""))
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Supply an existing verified HTTP(S) final_url.")
        kws = group["keywords"]
        if not kws or len({(k["text"], k.get("match_type", "EXACT")) for k in kws}) != len(kws):
            raise ValueError("Keywords must be nonempty and unique.")
        for kw in kws:
            if not kw["text"].strip() or kw.get("match_type", "EXACT") not in ("EXACT", "PHRASE", "BROAD"):
                raise ValueError("Invalid keyword text or match_type.")
            if kw["text"].startswith("[") or kw["text"].endswith("]"):
                raise ValueError("Use literal keyword text without UI brackets.")


def rsa_payload(spec, group):
    return {
        "final_urls": [group.get("final_url", spec.get("final_url"))],
        "responsive_search_ad": {
            "headlines": [{"text": h, **({"pinned_field": "HEADLINE_1"} if i == 0 else {})}
                          for i, h in enumerate(group["headlines"])],
            "descriptions": [{"text": d} for d in group["descriptions"]],
            **{k: group[k] for k in ("path1", "path2") if group.get(k)}
        }
    }


def normalized_ad(ad):
    rsa = ad.get("responsive_search_ad", {})
    return {"final_urls": ad.get("final_urls", []), "responsive_search_ad": {
        "headlines": [{"text": x["text"], **({"pinned_field": x["pinned_field"]}
                        if x.get("pinned_field") not in (None, "UNSPECIFIED") else {})}
                      for x in rsa.get("headlines", [])],
        "descriptions": [{"text": x["text"], **({"pinned_field": x["pinned_field"]}
                         if x.get("pinned_field") not in (None, "UNSPECIFIED") else {})}
                         for x in rsa.get("descriptions", [])],
        **{k: rsa[k] for k in ("path1", "path2") if rsa.get(k)}
    }}


def search_plan(cid, campaign_id, spec, groups, keywords, ads):
    validate_spec(spec)
    campaign = f"customers/{cid}/campaigns/{campaign_id}"
    ops = []
    for index, group in enumerate(spec.get("ad_groups", []), 1):
        matches = [r["ad_group"] for r in groups if r["ad_group"]["name"] == group["name"]
                   and r["ad_group"]["status"] != "REMOVED"]
        if len(matches) > 1:
            raise ValueError("Duplicate existing ad-group name: " + group["name"])
        expected_ad = rsa_payload(spec, group)
        expected_kw = sorted((k["text"], k.get("match_type", "EXACT")) for k in group["keywords"])
        if matches:
            existing = matches[0]
            rn = existing["resource_name"]
            current_k = [r["ad_group_criterion"] for r in keywords
                         if r["ad_group"]["resource_name"] == rn
                         and r["ad_group_criterion"]["status"] != "REMOVED"
                         and not r["ad_group_criterion"].get("negative")]
            current_a = [r["ad_group_ad"] for r in ads
                         if r["ad_group"]["resource_name"] == rn
                         and r["ad_group_ad"]["status"] != "REMOVED"]
            if not (existing["status"] == "PAUSED"
                    and sorted((k["keyword"]["text"], k["keyword"]["match_type"])
                               for k in current_k) == expected_kw
                    and all(k["status"] == "PAUSED" for k in current_k)
                    and len(current_a) == 1 and current_a[0]["status"] == "PAUSED"
                    and normalized_ad(current_a[0]["ad"]) == expected_ad):
                raise ValueError("Existing group differs from spec; inspect and explicitly "
                                 "update it instead of replacing history: " + group["name"])
            continue
        rn = f"customers/{cid}/adGroups/{-index}"
        ops.append({"ad_group_operation": {"create": {
            "resource_name": rn, "name": group["name"], "campaign": campaign,
            "status": "PAUSED", "type": "SEARCH_STANDARD"
        }}})
        for kw in group["keywords"]:
            ops.append({"ad_group_criterion_operation": {"create": {
                "ad_group": rn, "status": "PAUSED",
                "keyword": {"text": kw["text"], "match_type": kw.get("match_type", "EXACT")}
            }}})
        ops.append({"ad_group_ad_operation": {"create": {
            "ad_group": rn, "status": "PAUSED", "ad": expected_ad
        }}})
    return {"customer_id": cid, "campaign_id": str(campaign_id), "operations": ops}


def asset_plan(cid, campaign_id, spec, assets, links):
    campaign = f"customers/{cid}/campaigns/{campaign_id}"
    requested = []
    for s in spec.get("sitelinks", []):
        url = s["final_url"]
        if urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
            raise ValueError("Sitelinks require verified absolute HTTP(S) URLs.")
        payload = {"link_text": s["text"], **{k: s[k] for k in ("description1", "description2") if s.get(k)}}
        requested.append(("SITELINK", "sitelink_asset", payload, [url]))
    for text in spec.get("callouts", []):
        requested.append(("CALLOUT", "callout_asset", {"callout_text": text}, []))
    for snippet in spec.get("structured_snippets", []):
        requested.append(("STRUCTURED_SNIPPET", "structured_snippet_asset", snippet, []))
    ops, seen = [], set()
    for index, (kind, key, payload, urls) in enumerate(requested, 1001):
        import json
        fingerprint = json.dumps([kind, payload, urls], sort_keys=True)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        existing = sorted(r["asset"]["resource_name"] for r in assets
                          if r["asset"].get(key) == payload
                          and r["asset"].get("final_urls", []) == urls)
        if existing:
            rn = existing[0]
        else:
            rn = f"customers/{cid}/assets/{-index}"
            ops.append({"asset_operation": {"create": {
                "resource_name": rn, key: payload,
                **({"final_urls": urls} if urls else {})
            }}})
        attached = [r["campaign_asset"] for r in links
                    if r["campaign_asset"]["asset"] == rn
                    and r["campaign_asset"]["field_type"] == kind
                    and r["campaign_asset"]["status"] != "REMOVED"]
        if len(attached) > 1:
            raise ValueError("Duplicate asset associations; inspect before changing.")
        if attached:
            if attached[0]["status"] != "ENABLED":
                raise ValueError("Existing asset association is not enabled; inspect first.")
        else:
            ops.append({"campaign_asset_operation": {"create": {
                "campaign": campaign, "asset": rn, "field_type": kind, "status": "ENABLED"
            }}})
    return {"customer_id": cid, "campaign_id": str(campaign_id), "operations": ops}
