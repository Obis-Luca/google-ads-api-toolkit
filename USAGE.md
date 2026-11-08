# Usage

Global options go before the subcommand. Use ads-toolkit COMMAND --help for arguments.

## Audit and query

    mkdir -p private
    ads-toolkit --auth mcp --customer-id 1234567890 audit --campaign-id 999 --out private/before.json
    ads-toolkit --auth mcp --customer-id 1234567890 query --query-file examples/query.gaql --out private/query.json

Audit includes settings, budgets, targeting, groups, keywords, ads, assets, shared negatives, conversions/goals, last-30-day metrics and available recent change events. Some resources are account-wide to expose inherited context. Change history uses a bounded 29-day interval and a 10,000-row maximum. This is not a lifetime archive.

Incomplete sections are recorded under errors and cause a nonzero exit. Do not treat a partial audit as complete. Queries paginate; large exports may use substantial memory.

## Search planning

Copy examples/search-spec.json into private/spec.json and replace placeholders. The existing campaign must be a paused Search campaign.

Each group has one RSA and one or more keywords. Supply 3–15 unique headlines (30 characters maximum each), 2–4 unique descriptions (90 maximum each), and paths of at most 15 characters. Keywords use literal text without square brackets. EXACT is the default match type.

The first headline is pinned to HEADLINE_1; everything else stays unpinned. No text is rewritten or truncated. A group can override the shared final_url. Verify URLs and offers yourself; the planner does not fetch or edit websites.

    ads-toolkit --auth mcp --customer-id 1234567890 plan --campaign-id 999 --spec private/spec.json --out private/plan.json
    ads-toolkit --auth mcp --customer-id 1234567890 mutate --file private/plan.json
    ads-toolkit --auth mcp --customer-id 1234567890 mutate --file private/plan.json --apply
    ads-toolkit --auth mcp --customer-id 1234567890 verify --campaign-id 999 --spec private/spec.json --out private/qa.json

Matching existing groups generate no operations. Conflicting or duplicate names stop planning. Shared assets are reused by exact content/URL and linked to the paused campaign.

Generate a fresh plan after applying. Raw creation requests are not replay-safe. Verify compares the supplied spec and records policy status; it does not certify unrelated entities, negative conflicts or website tracking.

## Generic mutations

examples/mutations.json shows a status update and exact keyword creation. A plan contains customer_id and an operations array.

    ads-toolkit --auth mcp --customer-id 1234567890 mutate --file private/operations.json
    ads-toolkit --auth mcp --customer-id 1234567890 mutate --file private/operations.json --apply

The supported operations are those in the installed SDK's MutateOperation: groups, criteria, ads, assets, campaign settings, budgets, goals and more. Updates need explicit field masks. Requests use partial_failure=false and validate before committing. Removal uses Google's REMOVED state and retains historical reporting; use examples/remove-group.json only within an explicitly authorized task.

## Other services

Use service-specific calls for operations outside unified mutations, such as editing an existing RSA:

    ads-toolkit --auth mcp --customer-id 1234567890 call --service AdService --method mutate_ads --request-type MutateAdsRequest --file examples/update-rsa.json

Replace example IDs and text; append --apply to commit. JSON uses protobuf field names, enum strings and comma-separated field mask strings with lowerCamelCase paths (for example finalUrls,responsiveSearchAd.headlines). Unknown fields and cross-customer references are rejected.

RPCs with validate_only validate by default. Other methods starting get_, list_ or search are read-only. Other RPCs without validation require both --apply and --ack-no-validation. Read their official API contract first. Multi-step workflows such as batch jobs are not automatically orchestrated or atomic across calls.

## Discover SDK capabilities

These inspect installed SDK types locally without credentials:

    ads-toolkit services
    ads-toolkit schema MutateOperation
    ads-toolkit schema AdGroup
    ads-toolkit methods AdGroupService

Live GAQL field metadata:

    ads-toolkit --auth mcp fields --query "SELECT name, selectable WHERE name LIKE 'ad_group.%'"

Exit 0 means success or successful validation; inspect committed to distinguish execution. Exit 1 means an error, incomplete audit or failed verification. Usage errors exit 2. Output files are not overwritten automatically.

Never blindly retry a timed-out write. Review policy status and signup event firing before activating a campaign. No toolkit command changes a website or fabricates conversions.
