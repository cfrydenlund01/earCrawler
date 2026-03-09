# Hybrid Retrieval Design

Status: implemented as an experimental, off-by-default retrieval mode.

As of March 6, 2026, this does not change the KG quarantine status and is not a production commitment by itself. Operators should treat hybrid retrieval as an explicit opt-in until the runtime gate in `docs/kg_quarantine_exit_gate.md` is formally passed and recorded.

## Goal

Add a measurable BM25+dense retrieval path without weakening the current supported RAG contract:

- keep dense retrieval as the default,
- make hybrid retrieval explicit,
- preserve deterministic offline evaluation surfaces,
- keep KG optional and unchanged by default.

## Architecture

Hybrid retrieval adds a retrieval mode above the existing dense backend selection.

- Dense mode:
  - uses the existing dense retriever over the configured backend (`faiss` or `bruteforce`)
- Hybrid mode:
  - runs the same dense retrieval pass,
  - builds a lightweight BM25 view from the existing retrieval metadata rows,
  - fuses dense and BM25 ranks with reciprocal rank fusion (RRF, `k=60`),
  - keeps explicit-citation boosting after fusion so direct section cites still win deterministically.

This design intentionally reuses the existing `index.meta.json` rows instead of introducing a second packaged lexical index artifact. That keeps the packaging surface small and avoids repo-relative resource assumptions.

## Runtime Surface

Runtime selection is explicit:

- `EARCRAWLER_RETRIEVAL_MODE=dense`
- `EARCRAWLER_RETRIEVAL_MODE=hybrid`

Dense backend selection remains separate:

- `EARCRAWLER_RETRIEVAL_BACKEND=faiss`
- `EARCRAWLER_RETRIEVAL_BACKEND=bruteforce`

The supported API and CLI paths consume the same retriever object, so the mode applies consistently across:

- `service.api_server`
- `py -m earCrawler.cli llm ask ...`
- `py -m earCrawler.cli eval run-rag ...`
- `py -m earCrawler.cli eval fr-coverage ...`

## Evaluation

Offline deterministic measurement:

- `py -m earCrawler.cli eval fr-coverage --retrieval-mode dense`
- `py -m earCrawler.cli eval fr-coverage --retrieval-mode hybrid`

Production-like RAG measurement:

- `py -m earCrawler.cli eval run-rag --retrieval-mode dense`
- `py -m earCrawler.cli eval run-rag --retrieval-mode hybrid`
- `python scripts/eval/eval_rag_llm.py --dataset-id <id> --retrieval-compare`

The eval artifacts record retrieval mode and fusion metadata in provenance so dense and hybrid runs can be compared directly.

## Non-goals

- No default-on KG dependency
- No learned reranker
- No new lexical model training
- No change to strict-output, grounding, or refusal behavior
