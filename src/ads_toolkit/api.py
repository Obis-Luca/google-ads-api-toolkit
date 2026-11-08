"""Strict protobuf JSON, scoped requests, and validation before mutation."""
import hashlib
import importlib
import inspect
import json
import os
import pkgutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from google.auth.credentials import AnonymousCredentials
from google.ads.googleads.client import GoogleAdsClient
from google.protobuf.json_format import MessageToDict, ParseDict


def pb(message):
    return message._pb if hasattr(message, "_pb") else message


def to_dict(message):
    return MessageToDict(pb(message), preserving_proto_field_name=True)


def parse(client, type_name, data):
    message = client.get_type(type_name)
    ParseDict(data, pb(message), ignore_unknown_fields=False)
    return message


def offline_client(version=None):
    return GoogleAdsClient(credentials=AnonymousCredentials(), developer_token="offline",
                           use_proto_plus=True, version=version)


def query(client, cid, gaql):
    service = client.get_service("GoogleAdsService")
    return [to_dict(row) for row in service.search(
        customer_id=cid, query=gaql, timeout=60
    )]


def check_scope(value, cid):
    """Reject cross-customer resource names, including those nested in JSON."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ("customer_id", "customerId") and str(item) != cid:
                raise ValueError("Request customer_id differs from --customer-id.")
            check_scope(item, cid)
    elif isinstance(value, list):
        for item in value:
            check_scope(item, cid)
    elif isinstance(value, str) and value.startswith("customers/"):
        owner = value.split("/")[1]
        if owner != cid:
            raise ValueError("Cross-customer resource reference rejected.")


class Journal:
    def __init__(self, base):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self.path = Path(base) / (stamp + "-" + uuid.uuid4().hex[:8])
        self.path.mkdir(parents=True, mode=0o700)

    def save(self, name, data):
        path = self.path / name
        # Explicit restrictive file mode even when imported outside the CLI.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")


def execute(client, service_name, method_name, type_name, data, *,
            cid=None, apply=False, ack_no_validation=False, journal=None):
    request = parse(client, type_name, data)
    fields = pb(request).DESCRIPTOR.fields_by_name
    if "customer_id" in fields:
        if not cid:
            raise ValueError("--customer-id is required for this request.")
        if request.customer_id and request.customer_id != cid:
            raise ValueError("Request customer_id differs from --customer-id.")
        request.customer_id = cid
    payload = to_dict(request)
    if cid:
        check_scope(payload, cid)
    if "partial_failure" in fields and getattr(request, "partial_failure"):
        raise ValueError("Partial-failure writes are not supported; use atomic requests.")
    can_validate = "validate_only" in fields
    read_only = method_name.startswith(("get_", "list_", "search"))
    if not can_validate and not read_only and not (apply and ack_no_validation):
        raise ValueError("This RPC cannot validate. Use --apply --ack-no-validation only "
                         "after reviewing its documented side effects.")
    if can_validate:
        request.validate_only = True
    service = client.get_service(service_name)
    # Only generated public RPCs; block attributes, transport access, helpers.
    method = getattr(service, method_name, None)
    if method_name.startswith("_") or not callable(method) or "request" not in inspect.signature(method).parameters:
        raise ValueError("Expected a generated SDK RPC with a request parameter.")
    intent = dict(payload)
    intent.pop("validate_only", None)
    digest = hashlib.sha256(json.dumps(
        {"service": service_name, "method": method_name, "request": intent},
        sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    if journal:
        journal.save("request.json", {"service": service_name, "method": method_name,
                                     "type": type_name, "sha256": digest,
                                     "request": to_dict(request)})
    if can_validate:
        method(request=request, timeout=90, retry=None)
        if journal:
            journal.save("validation.json", {"passed": True, "sha256": digest})
        if not apply:
            return {"validated": True, "committed": False, "sha256": digest}
        request.validate_only = False
    # Never automatically retry a write: a lost response can follow a commit.
    if journal and not read_only:
        journal.save("commit-attempt.json", {"sha256": digest,
                                            "inspect_account_before_retry": True})
    response = method(request=request, timeout=90, retry=None)
    if hasattr(response, "_pb") or hasattr(response, "DESCRIPTOR"):
        result = to_dict(response)
    else:
        result = [to_dict(row) for row in response]
    out = {"validated": can_validate, "committed": not read_only,
           "sha256": digest, "response": result}
    if journal:
        journal.save("response.json", out)
    return out


def mutate(client, cid, plan, *, apply=False, journal=None):
    if plan.get("customer_id") != cid:
        raise ValueError("Plan customer_id must equal --customer-id.")
    ops = plan.get("operations")
    if not isinstance(ops, list):
        raise ValueError("Plan requires an operations array.")
    if not ops:
        return {"validated": True, "committed": False, "operations": 0}
    for op in ops:
        if not isinstance(op, dict) or len(op) != 1:
            raise ValueError("Each operation must specify exactly one operation type.")
    return execute(client, "GoogleAdsService", "mutate", "MutateGoogleAdsRequest",
                   {"customer_id": cid, "mutate_operations": ops, "partial_failure": False},
                   cid=cid, apply=apply, journal=journal)


def services(version=None):
    # Discover installed API versions without hardcoding the SDK default.
    from google.ads.googleads import client as sdk
    version = version or sdk._DEFAULT_VERSION
    package = importlib.import_module(f"google.ads.googleads.{version}.services.services")
    return sorted(m.name for m in pkgutil.iter_modules(package.__path__))


def schema(client, name):
    descriptor = pb(client.get_type(name)).DESCRIPTOR
    def field(f):
        out = {"name": f.name, "type": f.type,
               "repeated": f.is_repeated}
        if f.message_type:
            out["message"] = f.message_type.full_name
        if f.enum_type:
            out["enum"] = [v.name for v in f.enum_type.values]
        if f.containing_oneof:
            out["oneof"] = f.containing_oneof.name
        return out
    return {"type": descriptor.full_name, "fields": [field(f) for f in descriptor.fields]}


def methods(client, name):
    service = client.get_service(name)
    return {n: str(inspect.signature(getattr(service, n)))
            for n in dir(type(service))
            if not n.startswith("_") and callable(getattr(service, n))
            and "request" in inspect.signature(getattr(service, n)).parameters}
