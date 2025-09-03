# Monitoring

The scheduled monitor checks a JSON watchlist and captures upstream deltas for
Trade.gov entities and Federal Register EAR content. Each watch item includes
API specific parameters such as search queries and page limits. The monitor
normalizes responses, computes a SHA-256 digest and compares it to the last
recorded state in `monitor/state.json`.

On change the run writes `monitor/upstream-status.json` and a dated
`monitor/delta-YYYYMMDD.json` containing the new payloads.

To add a new item edit `monitor/watchlist.json` and provide either a
`tradegov` or `federalregister` section entry. Fields not relevant to tests may
be omitted.
