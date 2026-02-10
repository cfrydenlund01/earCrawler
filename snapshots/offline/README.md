# Offline Snapshots (Local Working Copy)

This directory is the recommended local layout for approved offline snapshots:
- `snapshots/offline/<snapshot_id>/manifest.json` (tracked)
- `snapshots/offline/<snapshot_id>/snapshot.jsonl` (not tracked; external)

The payload is intentionally gitignored to avoid accidental commits of large, drifting inputs.
Use `py -m earCrawler.cli rag-index validate-snapshot --snapshot snapshots/offline/<snapshot_id>/snapshot.jsonl`
to validate the payload+manifest pair before building the retrieval corpus or FAISS index.

