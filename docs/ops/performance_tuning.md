# Performance tuning

The performance harness uses Apache Jena TDB2 and Fuseki. Key tuning knobs for
Windows runners are tracked in `perf/config/fuseki_tuning.yml`:

- `jvm_heap`: sets a fixed 1 GB heap to avoid paging.
- `gc`: G1 is used for predictable pause times.
- `fuseki_timeout_ms`: hard timeout applied to every query.
- `threads`: worker thread count for Fuseki.
- `tdb2`: read ahead and page size hints when building the dataset.

Budgets for queries and resource usage live in `perf/config/perf_budgets.yml`.
These budgets are enforced during CI.  They define p95 and p99 targets for each
query group along with CPU and memory ceilings.
