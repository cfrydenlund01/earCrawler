# Performance workflows

Performance runs use deterministic synthetic datasets and can operate offline.

## Generate data

```cmd
earctl perf synth --scale M
```

## Execute runs

```cmd
earctl perf run --scale M --cold --warm
```

Reports are written to `kg/reports/perf-report.json` and a human summary in
`kg/reports/perf-summary.txt`.

## Updating baselines

After adjusting budgets or improving queries run the suite locally and replace
`perf/baselines/baseline_S.json` with the new report summary.
