# Setup

Install with README.md. You need network access to Google OAuth/Ads endpoints and an authorized Google Ads identity. These scripts do not grant new account permissions.

## Existing local MCP authentication

    ads-toolkit --auth mcp --customer-id 1234567890 query --gaql "SELECT customer.id, customer.descriptive_name FROM customer"

This reads allowed credential environment settings from the mcp_servers.google-ads.env table in ~/.codex/config.toml and uses Application Default Credentials. It does not launch the MCP or copy credentials into this repository. Override with --mcp-config PATH and --mcp-server NAME. This mode supports a local ADC-based configuration, not arbitrary remote MCP OAuth sessions.

## Other authentication options

ADC: use your existing Google login with the adwords scope. Set GOOGLE_APPLICATION_CREDENTIALS to an authorized credential file outside this repo and GOOGLE_ADS_DEVELOPER_TOKEN as required by your API setup.

    ads-toolkit --auth adc --customer-id 1234567890 query --query-file examples/query.gaql

Official SDK YAML or environment configuration:

    ads-toolkit --auth yaml --config /secure/path/google-ads.yaml --customer-id 1234567890 query --query-file examples/query.gaql
    ads-toolkit --auth env --customer-id 1234567890 query --query-file examples/query.gaql

See [Google's configuration reference](https://developers.google.com/google-ads/api/docs/client-libs/python/configuration) for OAuth client ID, client secret, refresh token and developer token configuration. The CLI does not automatically load .env files.

For a manager account, add --login-customer-id MANAGER_ID before the command. The --customer-id identifies the account you operate on. Hyphenated IDs are accepted.

## Verify and protect credentials

Start with a read-only query, then validate the actual mutation payload without --apply. A successful read does not prove mutation permission.

Never commit or print OAuth files, tokens, SDK YAML, or MCP configuration. Account exports and requests also contain private information: keep them under private/ or artifacts/ (ignored by Git).

Mutate/call records are stored under artifacts/ by default; --output-dir overrides this. SDK request/header logging and raw authentication exception bodies are suppressed. If a write times out, inspect the account before retrying; it may already have committed.
