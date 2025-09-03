# Reconciliation

This module performs deterministic entity reconciliation between sources.  The
normalisation pipeline applies case‐folding, Unicode NFC, punctuation stripping
and stop‑word removal before generating blocking keys and similarity features.

Scores are computed from multiple features using weights defined in
`kg/reconcile/rules.yml`.  Hard constraints such as country mismatch stop an
automatic merge regardless of the score.

Thresholds are configured with `high` and `low` bounds.  Pairs scoring above the
high threshold auto‑merge; those between the two thresholds require review; all
others are rejected.

Override lists (`whitelist.csv` and `blacklist.csv`) contain deterministic
allow/deny pairs.  After a run the engine writes:

* `kg/reconcile/idmap.csv` – canonical to source mappings
* `kg/reconcile/decisions.jsonl.gz` – feature vectors and decisions
* `kg/reports/reconcile-summary.json` – counts by decision
* `kg/reports/reconcile-conflicts.json` – near‑threshold cases
* `kg/delta/reconcile-merged.ttl` – RDF `owl:sameAs` triples

Rollback can be performed with `earctl reconcile rollback --canonical-id <id>`
which prints the mappings that must be removed.
