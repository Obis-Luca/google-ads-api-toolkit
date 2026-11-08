"""Command line interface; no mutation occurs at import or startup."""
import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path

from . import __version__
from .auth import customer_id, load_client
from .api import (Journal, execute, methods, mutate, offline_client, query,
                  schema, services)
from .audit import audit
from .planner import search_plan, asset_plan


def positive_id(value):
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise argparse.ArgumentTypeError("Expected a positive numeric resource ID.")
    return value


def read_json(path):
    return json.loads(Path(path).read_text())


def save_json(path, data):
    target = Path(path)
    # Plans and exports can contain sensitive account data; avoid overwrites.
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def parser():
    p = argparse.ArgumentParser(description="Google Ads API toolkit; writes validate by default.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--auth", choices=["adc", "mcp", "env", "yaml"], default="adc")
    p.add_argument("--config", help="SDK YAML path, only for --auth yaml")
    p.add_argument("--mcp-config", default="~/.codex/config.toml")
    p.add_argument("--mcp-server", default="google-ads")
    p.add_argument("--api-version", help="e.g. v26; defaults to installed SDK default")
    p.add_argument("--customer-id", type=customer_id)
    p.add_argument("--login-customer-id", type=customer_id)
    p.add_argument("--output-dir", default="artifacts")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("services", help="List installed SDK services offline")
    s = sub.add_parser("schema", help="Inspect a request/resource message offline")
    s.add_argument("type_name")
    s = sub.add_parser("methods", help="Inspect service RPC signatures offline")
    s.add_argument("service")
    s = sub.add_parser("fields", help="Query live GAQL field metadata")
    s.add_argument("--query", required=True)
    s = sub.add_parser("query")
    q = s.add_mutually_exclusive_group(required=True)
    q.add_argument("--gaql")
    q.add_argument("--query-file")
    s.add_argument("--out")
    s = sub.add_parser("audit")
    s.add_argument("--campaign-id", required=True, type=positive_id)
    s.add_argument("--out", required=True)
    for command in ("plan", "verify"):
        s = sub.add_parser(command, help="Plan/verify paused Search groups and shared assets")
        s.add_argument("--campaign-id", required=True, type=positive_id)
        s.add_argument("--spec", required=True)
        s.add_argument("--out", required=True)
    s = sub.add_parser("mutate")
    s.add_argument("--file", required=True)
    s.add_argument("--apply", action="store_true")
    s = sub.add_parser("call", help="Invoke any generated SDK RPC using strict JSON")
    s.add_argument("--service", required=True)
    s.add_argument("--method", required=True)
    s.add_argument("--request-type", required=True)
    s.add_argument("--file", required=True)
    s.add_argument("--apply", action="store_true")
    s.add_argument("--ack-no-validation", action="store_true")
    return p


def snapshots(client, cid, campaign_id):
    condition = f" WHERE campaign.id = {campaign_id}"
    group = query(client, cid, "SELECT ad_group.resource_name, ad_group.name, ad_group.status "
                  "FROM ad_group" + condition + " AND ad_group.status != 'REMOVED'")
    kw = query(client, cid, "SELECT ad_group.resource_name, ad_group_criterion.status, "
               "ad_group_criterion.negative, ad_group_criterion.keyword.text, "
               "ad_group_criterion.keyword.match_type FROM ad_group_criterion"
               + condition + " AND ad_group_criterion.type = 'KEYWORD' "
               "AND ad_group_criterion.status != 'REMOVED'")
    ads = query(client, cid, "SELECT ad_group.resource_name, ad_group_ad.status, "
                "ad_group_ad.ad.final_urls, ad_group_ad.ad.responsive_search_ad.headlines, "
                "ad_group_ad.ad.responsive_search_ad.descriptions, "
                "ad_group_ad.ad.responsive_search_ad.path1, "
                "ad_group_ad.ad.responsive_search_ad.path2, "
                "ad_group_ad.policy_summary.review_status, "
                "ad_group_ad.policy_summary.approval_status FROM ad_group_ad" + condition
                + " AND ad_group_ad.status != 'REMOVED'")
    return group, kw, ads


def run(args):
    if args.command in ("services", "schema", "methods"):
        if args.command == "services":
            return services(args.api_version)
        offline = offline_client(args.api_version)
        if args.command == "schema":
            return schema(offline, args.type_name)
        return methods(offline, args.service)
    if args.command not in ("call", "fields") and not args.customer_id:
        raise ValueError("--customer-id is required.")
    client = load_client(args)
    cid = args.customer_id
    if args.command == "fields":
        return [__import__("ads_toolkit.api", fromlist=["to_dict"]).to_dict(f)
                for f in client.get_service("GoogleAdsFieldService").search_google_ads_fields(
                    query=args.query, timeout=60)]
    if args.command == "query":
        gaql = args.gaql or Path(args.query_file).read_text()
        result = query(client, cid, gaql)
        if args.out:
            save_json(args.out, result)
        return result
    if args.command == "audit":
        result = audit(client, cid, args.campaign_id)
        save_json(args.out, result)
        return {"out": args.out, "complete": result["complete"], "errors": result["errors"]}
    if args.command in ("plan", "verify"):
        campaign = query(client, cid, "SELECT campaign.id, campaign.status, "
                         "campaign.advertising_channel_type FROM campaign WHERE campaign.id = "
                         + args.campaign_id)
        if len(campaign) != 1 or campaign[0]["campaign"]["status"] != "PAUSED":
            raise ValueError("The existing campaign must be PAUSED before staging.")
        if campaign[0]["campaign"]["advertising_channel_type"] != "SEARCH":
            raise ValueError("The Search planner requires a Search campaign.")
        spec = read_json(args.spec)
        groups, kw, ads = snapshots(client, cid, args.campaign_id)
        plan = search_plan(cid, args.campaign_id, spec, groups, kw, ads)
        if any(spec.get(k) for k in ("sitelinks", "callouts", "structured_snippets")):
            assets = query(client, cid, "SELECT asset.resource_name, asset.final_urls, "
                           "asset.sitelink_asset.link_text, asset.sitelink_asset.description1, "
                           "asset.sitelink_asset.description2, asset.callout_asset.callout_text, "
                           "asset.structured_snippet_asset.header, "
                           "asset.structured_snippet_asset.values FROM asset")
            links = query(client, cid, "SELECT campaign.id, campaign_asset.asset, "
                          "campaign_asset.field_type, campaign_asset.status FROM campaign_asset "
                          "WHERE campaign.id = " + args.campaign_id)
            plan["operations"].extend(asset_plan(cid, args.campaign_id, spec, assets, links)["operations"])
        if args.command == "verify":
            result = {"verified": not plan["operations"],
                      "missing_operations": len(plan["operations"]),
                      "ads": ads, "groups": groups}
            save_json(args.out, result)
            return result
        save_json(args.out, plan)
        return {"out": args.out, "operations": len(plan["operations"])}
    journal = Journal(args.output_dir)
    try:
        if args.command == "mutate":
            result = mutate(client, cid, read_json(args.file), apply=args.apply, journal=journal)
        else:
            result = execute(client, args.service, args.method, args.request_type,
                             read_json(args.file), cid=cid, apply=args.apply,
                             ack_no_validation=args.ack_no_validation, journal=journal)
        return {"journal": str(journal.path), **result}
    except Exception as error:
        journal.save("failure.json", {"type": type(error).__name__,
                     "request_id": getattr(error, "request_id", None),
                     "inspect_account_before_retry": args.apply})
        raise


def main():
    os.umask(0o077)
    # The SDK can log request headers and payloads. This CLI does not enable it.
    logging.disable(logging.CRITICAL)
    args = parser().parse_args()
    try:
        result = run(args)
        print(json.dumps(result, indent=2))
        if isinstance(result, dict) and (result.get("complete") is False or result.get("verified") is False):
            return 1
        return 0
    except Exception as error:
        if hasattr(error, "failure"):
            output = {"error": type(error).__name__, "request_id": error.request_id,
                      "codes": [str(e.error_code).strip() for e in error.failure.errors]}
        elif isinstance(error, (ValueError, argparse.ArgumentTypeError)):
            output = {"error": type(error).__name__, "message": str(error)}
        else:
            output = {"error": type(error).__name__,
                      "message": "Inspect local setup and request schema. Credentials and raw "
                                 "transport/auth errors are intentionally not printed."}
        print(json.dumps(output), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
