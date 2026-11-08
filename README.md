# Google Ads API Toolkit — v1

A small Python CLI for Google Ads operations missing from your MCP installation.

- Audit campaigns and run GAQL queries.
- Stage paused Search groups, keywords and RSAs from supplied copy.
- Deduplicate shared sitelinks, callouts and structured snippets.
- Submit generic create/update/remove operations.
- Call other installed Google Ads SDK services directly.

This is a companion CLI, not an MCP server. Dedicated workflows focus on Search; the generic bridge reaches other requests supported by the SDK and your account permissions.

## Install

Requires Python 3.11+.

    git clone https://github.com/Obis-Luca/google-ads-api-toolkit.git
    cd google-ads-api-toolkit
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -e .
    ads-toolkit --help

Read [SETUP.md](SETUP.md), [USAGE.md](USAGE.md), and [AGENTS.md](AGENTS.md).

## Quick start

All IDs, copy and URLs in examples are fictional placeholders. Replace them before use. Global options precede the subcommand.

    mkdir -p private
    ads-toolkit --auth mcp --customer-id 1234567890 audit --campaign-id 999 --out private/before.json

Edit a copy of examples/search-spec.json with approved copy and existing verified destinations, then:

    ads-toolkit --auth mcp --customer-id 1234567890 plan --campaign-id 999 --spec private/spec.json --out private/plan.json
    ads-toolkit --auth mcp --customer-id 1234567890 mutate --file private/plan.json
    ads-toolkit --auth mcp --customer-id 1234567890 mutate --file private/plan.json --apply
    ads-toolkit --auth mcp --customer-id 1234567890 verify --campaign-id 999 --spec private/spec.json --out private/qa.json

Without --apply, mutations only validate. With --apply, validation runs again before committing.

## v1 limits

The planner copies text verbatim and pins only the first headline. New groups, keywords and ads stay paused. It does not change budgets, targeting, bidding, conversions, campaign status, legacy groups or websites. Matching groups are skipped; conflicting groups require an explicit update.

Generate a fresh plan after every successful apply. Replaying raw creation payloads can create duplicates. API validation does not prove policy approval or conversion firing. No scheduler or background process is installed.

Tests run offline:

    python -m unittest discover -s tests -v

Tested with google-ads 35.x / API v26. Other API versions may require audit field adjustments.

Official references: [configuration](https://developers.google.com/google-ads/api/docs/client-libs/python/configuration), [mutations](https://developers.google.com/google-ads/api/docs/mutating/bulk-mutate), [RSAs](https://developers.google.com/google-ads/api/docs/responsive-search-ads/create-responsive-search-ads).
