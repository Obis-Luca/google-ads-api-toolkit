"""Explicit authentication sources; never print loaded configuration."""
import os
import tomllib
from pathlib import Path

from google.ads.googleads.client import GoogleAdsClient
import google.auth

ALLOWED_ENV = {
    "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_PROJECT_ID", "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
    "GOOGLE_ADS_LINKED_CUSTOMER_ID", "GOOGLE_ADS_CLIENT_ID",
    "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN",
    "GOOGLE_ADS_USE_PROTO_PLUS",
}


def customer_id(value):
    value = str(value).replace("-", "")
    if len(value) != 10 or not value.isascii() or not value.isdigit():
        raise ValueError("Customer IDs must contain exactly ten digits.")
    return value


def load_client(args):
    if args.auth == "mcp":
        config = tomllib.loads(Path(args.mcp_config).expanduser().read_text())
        env = config["mcp_servers"][args.mcp_server].get("env", {})
        # Load credential settings, never run a configured MCP command or shell.
        for key, value in env.items():
            if key in ALLOWED_ENV:
                os.environ[key] = str(value)
    if args.auth == "yaml":
        if not args.config:
            raise ValueError("--auth yaml requires --config.")
        client = GoogleAdsClient.load_from_storage(args.config, version=args.api_version)
    elif args.auth == "env":
        client = GoogleAdsClient.load_from_env(version=args.api_version)
    else:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/adwords"]
        )
        kwargs = {"credentials": credentials, "use_proto_plus": True,
                  "version": args.api_version}
        for key in ("developer_token", "login_customer_id", "linked_customer_id"):
            value = os.environ.get("GOOGLE_ADS_" + key.upper())
            if value:
                kwargs[key] = customer_id(value) if key.endswith("customer_id") else value
        client = GoogleAdsClient(**kwargs)
    client.use_proto_plus = True
    if args.login_customer_id:
        client.login_customer_id = customer_id(args.login_customer_id)
    return client
