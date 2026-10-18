# Source registry policy

Each source must have a named owner, source type, access mode, license/terms review status, permitted retention, refresh cadence, canonical documentation URL, and a documented outage behavior.

A source may be marked active only after an operator records the access method and terms review. Credentials are environment secrets, never source metadata. Connectors must preserve publication time, retrieval time, content hash, and provider identifiers.

Initial candidate source families for a future integration review: official humanitarian situation reports, Copernicus Sentinel catalog/assets, NASA FIRMS for its specific fire/hotspot use case, and a licensed commercial AIS provider. No integration is enabled merely because its name appears here.
