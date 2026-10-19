# ReliefWeb connector notes

- Provider API: https://apidoc.reliefweb.int/ (API v2).
- The adapter uses POST to https://api.reliefweb.int/v2/reports with the appname query parameter and a JSON query.
- Configure an app name only after provider registration/approval. Do not place credentials or other secrets in git.
- Configure an explicit country scope as country names accepted by the provider API. Keep page size and page count bounded.
- The adapter requests report metadata fields only and stores canonical URLs; it does not request or store report body content.
- Response paging uses totalCount for total query count, not count for one response.
- Source data and report content remain governed by provider/contributor terms. Review the applicable terms before activating a source; API accessibility is not a redistribution license.
- A report is not automatically interpreted as a verified fact. Documents enter source review, and event drafting, evidence linking, review and publication are separate steps.
