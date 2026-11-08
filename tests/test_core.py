import copy
import json
import unittest
from pathlib import Path
from ads_toolkit.api import offline_client, parse, to_dict, mutate, check_scope
from ads_toolkit.planner import search_plan, rsa_payload, asset_plan

CID = "1234567890"

class Service:
    def __init__(self): self.calls = []
    def mutate(self, request=None, **kwargs):
        self.calls.append(copy.deepcopy(to_dict(request)))
        return offline_client().get_type("MutateGoogleAdsResponse")

class Client:
    def __init__(self):
        self.sdk = offline_client("v26")
        self.service = Service()
    def get_type(self, name): return self.sdk.get_type(name)
    def get_service(self, name): return self.service

class CoreTests(unittest.TestCase):
    def spec(self):
        return json.loads((Path(__file__).resolve().parents[1] / "examples/search-spec.json").read_text())

    def test_copy_and_pinning(self):
        s = self.spec()
        plan = search_plan(CID, "999", s, [], [], [])
        ad = plan["operations"][-1]["ad_group_ad_operation"]["create"]
        rsa = ad["ad"]["responsive_search_ad"]
        self.assertEqual(ad["status"], "PAUSED")
        self.assertEqual([x["text"] for x in rsa["headlines"]], s["ad_groups"][0]["headlines"])
        self.assertEqual([x["text"] for x in rsa["descriptions"]], s["ad_groups"][0]["descriptions"])
        self.assertEqual(rsa["headlines"][0]["pinned_field"], "HEADLINE_1")
        self.assertTrue(all("pinned_field" not in t for t in rsa["headlines"][1:] + rsa["descriptions"]))
        parse(offline_client(), "MutateGoogleAdsRequest", {"customer_id": CID, "mutate_operations": plan["operations"]})

    def test_matching_group_noop_conflict_rejected(self):
        s = self.spec(); g = s["ad_groups"][0]
        rn = f"customers/{CID}/adGroups/111"
        groups = [{"ad_group": {"resource_name": rn, "name": g["name"], "status": "PAUSED"}}]
        kws = [{"ad_group": {"resource_name": rn}, "ad_group_criterion": {"status": "PAUSED", "keyword": g["keywords"][0]}}]
        ads = [{"ad_group": {"resource_name": rn}, "ad_group_ad": {"status": "PAUSED", "ad": rsa_payload(s, g)}}]
        self.assertEqual(search_plan(CID, "999", s, groups, kws, ads)["operations"], [])
        ads[0]["ad_group_ad"]["ad"]["responsive_search_ad"]["headlines"][0]["text"] = "Different"
        with self.assertRaises(ValueError): search_plan(CID, "999", s, groups, kws, ads)

    def test_validation_then_explicit_commit(self):
        plan = {"customer_id": CID, "operations": [{"ad_group_operation": {"update": {
            "resource_name": f"customers/{CID}/adGroups/111", "status": "PAUSED"}, "update_mask": "status"}}]}
        c = Client()
        self.assertFalse(mutate(c, CID, plan)["committed"])
        self.assertEqual(len(c.service.calls), 1)
        self.assertTrue(c.service.calls[0]["validate_only"])
        c = Client()
        self.assertTrue(mutate(c, CID, plan, apply=True)["committed"])
        self.assertEqual(len(c.service.calls), 2)
        self.assertTrue(c.service.calls[0]["validate_only"])
        self.assertFalse(c.service.calls[1].get("validate_only", False))

    def test_scope_and_examples(self):
        with self.assertRaises(ValueError): check_scope({"x": ["customers/0000000000/ads/1"]}, CID)
        with self.assertRaises(Exception): parse(offline_client(), "MutateGoogleAdsRequest", {"typo": True})
        plan = asset_plan(CID, "999", self.spec(), [], [])
        parse(offline_client(), "MutateGoogleAdsRequest", {"customer_id": CID, "mutate_operations": plan["operations"]})
        root = Path(__file__).resolve().parents[1] / "examples"
        for name in ["mutations.json", "remove-group.json"]:
            p = json.loads((root / name).read_text())
            parse(offline_client(), "MutateGoogleAdsRequest", {"customer_id": CID, "mutate_operations": p["operations"]})
        parse(offline_client(), "MutateAdsRequest", json.loads((root / "update-rsa.json").read_text()))

if __name__ == "__main__": unittest.main()
