# Agent instructions

Read README.md, SETUP.md and USAGE.md first. This is a companion CLI, not an MCP server.

- Use existing authorized authentication. Never expose credentials.
- Confirm account and campaign scope. Examples contain fictional IDs and URLs.
- Toolkit development does not authorize live account changes.
- Export a complete before-state before campaign changes.
- Preserve approved copy verbatim; never rewrite or truncate it.
- Use verified existing URLs; do not edit websites during Ads work.
- Plan, validate, explicitly apply within the user's scope, then read back.
- Preserve budgets, targeting, bidding and conversion settings unless authorized.
- Keep staged groups, keywords, ads and campaigns paused. Activation/removal must be authorized in the task context.
- Matching groups are skipped; conflicts need explicit reviewed updates.
- Regenerate plans after applying. Do not replay raw creates or retry uncertain writes blindly.
- Review inherited negatives, policy status and conversion event firing separately.
- Keep private account exports in private/ or artifacts/. Never commit real account data, SDK YAML, MCP configuration, OAuth files or tokens.
- The generic call escape hatch still requires task authorization. --ack-no-validation is an execution switch, not permission.
- Keep v1 small. Run offline tests with: python -m unittest discover -s tests -v
- Imports and tests must not contact Google. Use anonymous SDK clients and fake services.
