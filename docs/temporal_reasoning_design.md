# Temporal Reasoning Design

## Scope

Task 15 adds conservative temporal applicability handling to the supported RAG runtime surface:

- `earCrawler.rag.pipeline.answer_with_rag`
- API endpoints `POST /v1/rag/query` and `POST /v1/rag/answer`
- CLI `python -m earCrawler.cli llm ask`
- Eval datasets via `temporal.effective_date`

This change does not unquarantine KG-backed runtime features. The temporal decision is made from retrieval-corpus metadata first; KG can consume the same metadata later without becoming a production dependency here.

## Inputs

The runtime accepts an explicit `effective_date` in `YYYY-MM-DD` form.

If the caller does not provide one, the runtime may resolve one ISO date token directly from the question text. It does not attempt fuzzy date interpretation. The accepted logic is intentionally narrow:

- One ISO date in the question: treat it as the as-of date.
- Multiple ISO dates in the question: refuse.
- Explicit `effective_date` that conflicts with a question date: refuse.

This keeps temporal behavior explicit and testable rather than heuristic.

## Corpus Metadata

The retrieval corpus may carry these optional temporal fields:

- `snapshot_date`
- `effective_date`
- `effective_from`
- `effective_to`

Single-snapshot corpora can continue using canonical unsuffixed `doc_id` values because the whole corpus already represents one as-of state.

When multiple versions of the same section must coexist in one corpus, version identity belongs in `doc_id` and the canonical citation stays in `section_id`. A suffix such as `EAR-736.2#v2024-01-01` is valid. Chunk builders propagate that suffix to child chunks while leaving `section_id` canonical for citations and eval references.

## Retrieval Rules

When a temporal request is active, retrieval overfetches candidates before filtering.

Document classification uses explicit metadata only:

- `effective_from` / `effective_to`: authoritative applicability window.
- Otherwise `snapshot_date`: choose the latest snapshot at or before the requested date for each canonical `section_id`.
- No temporal metadata: `unknown`.

Statuses:

- `applicable`
- `future`
- `expired`
- `superseded`
- `unknown`

Only `applicable` documents enter the answer context. Future, expired, and superseded versions are excluded from prompt context.

## Refusal Rules

The runtime refuses with `label=unanswerable` when:

- the request has conflicting temporal anchors
- the question contains multiple ISO dates
- no retrieved evidence is applicable on the requested date
- only temporally ambiguous evidence is available

This is deliberate. The system should refuse rather than silently answer from the newest available text.

## Evaluation

Eval items can declare:

```json
{
  "temporal": {
    "effective_date": "2024-01-01"
  }
}
```

The eval runner passes that date through to `answer_with_rag`, and reports the effective date in per-item results so temporal runs remain auditable.
