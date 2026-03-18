# Shared RAG Orchestration Design

Prepared: March 16, 2026

Source of truth for this design: `docs/RunPass8.md`

## Goal

Extract one shared RAG orchestration layer so the pipeline path in
`earCrawler/rag/pipeline.py` and the API path in
`service/api_server/rag_service.py` stop reimplementing the same retrieval,
policy, prompt, and generation flow.

This is a design only. It does not widen the supported runtime surface and does
not implement feature graduation for quarantined KG/search behavior.

## Current duplication and drift

Today the shared low-level helpers already exist in:

- `earCrawler/rag/retrieval_runtime.py`
- `earCrawler/rag/llm_runtime.py`
- `earCrawler/rag/policy.py`

The duplication is in the orchestration layer above those helpers.

Observed split:

- `earCrawler/rag/pipeline.py`
  - drives retrieval
  - decides KG expansion
  - builds retrieval context bundle
  - builds prompt artifacts
  - applies refusal policy
  - executes generation
  - emits audit events
  - returns a large dict payload used by CLI/eval code
- `service/api_server/rag_service.py`
  - reimplements retrieval state handling
  - reimplements temporal-empty logic
  - reimplements prompt build + policy + generation
  - maps results to API models in `service/api_server/schemas/rag.py`

Concrete drift already visible:

- empty-retrieval behavior differs
  - pipeline currently calls `evaluate_generation_policy(..., refuse_on_empty=False)`
  - API currently calls `evaluate_generation_policy(..., refuse_on_empty=True)`
- KG expansion behavior differs
  - pipeline supports env/task-driven KG expansion
  - API answer path currently does not run KG expansion at all
- prompt context formatting differs
  - pipeline builds normalized context headers through
    `build_retrieval_context_bundle(...)`
  - API answer path builds prompt contexts separately through
    `build_prompt_contexts(...)`
- failure handling differs
  - pipeline can raise on strict retrieval
  - API converts disabled/broken retrieval into `503` responses
- audit behavior differs
  - pipeline emits required audit events
  - API path does not currently share that code

This is the exact seam that should be extracted. The low-level runtime helpers
are already reusable; the orchestration decisions are not.

## Minimal extraction seam

The seam should be placed between:

- adapter-specific concerns
- shared domain orchestration

Keep adapter-specific:

- HTTP request/response handling in `service/api_server/routers/rag.py`
- API cache management and cache keys in `service/api_server/rag_support.py`
- API lineage expansion for `/v1/rag/query`
- thread offload details for blocking retriever/LLM calls
- CLI JSON printing and Click exceptions
- audit sink wiring
- HTTP status mapping (`200` vs `422` vs `503`)

Move into one shared core module:

- retrieval execution result normalization
- temporal-state handling and retrieval-empty reason selection
- optional KG expansion decision
- prompt context construction used for generation
- refusal/thin-evidence policy application
- LLM request resolution and execution
- strict output validation
- canonical answer result assembly with timings

The API query route should reuse the shared retrieval stage, but lineage
assembly stays API-specific because it depends on service schemas and Fuseki
lineage response shaping.

## Proposed module

Add a new core module:

- `earCrawler/rag/orchestrator.py`

Recommended public surface:

```python
@dataclass(frozen=True)
class RagRequest:
    question: str
    top_k: int = 5
    effective_date: str | None = None
    task: str | None = None
    label_schema: str | None = None
    provider: str | None = None
    model: str | None = None
    generate: bool = True
    kg_expansion: bool | None = None
    strict_output: bool = True
    trace_id: str | None = None
    run_id: str | None = None
    refuse_on_empty: bool = True


@dataclass
class RetrievalOutcome:
    docs: list[dict]
    temporal_state: dict[str, object]
    warnings: list[dict[str, object]]
    rag_enabled: bool
    retriever_ready: bool
    retrieval_empty: bool
    retrieval_empty_reason: str | None
    failure_type: str | None
    disabled_reason: str | None
    retrieval_failure: Exception | None
    cache_hit: bool = False
    expires_at: datetime | None = None
    index_path: str | None = None
    model_name: str | None = None
    t_cache_ms: float = 0.0
    t_retrieve_ms: float = 0.0


@dataclass
class RagOutcome:
    retrieval: RetrievalOutcome
    context_bundle: RetrievalContextBundle
    generation: GenerationResult
    temporal_requested: bool
    effective_date: str | None
    timings: dict[str, float]
```

Recommended dependency injection surface:

```python
class RetrievalRunner(Protocol):
    async def __call__(self, request: RagRequest) -> RetrievalOutcome: ...


class KGExpansionRunner(Protocol):
    async def __call__(self, section_ids: list[str], request: RagRequest) -> list[KGExpansionSnippet]: ...


class GenerateRunner(Protocol):
    async def __call__(self, prompt: list[dict[str, str]] | list[dict], provider: str, model: str) -> str: ...
```

Recommended entry points:

```python
async def retrieve_only(request: RagRequest, *, retrieve: RetrievalRunner) -> RetrievalOutcome: ...

async def answer(request: RagRequest, *, retrieve: RetrievalRunner, generate: GenerateRunner, expand_kg: KGExpansionRunner | None = None, audit_hook: Callable[[RagOutcome], None] | None = None) -> RagOutcome: ...

def answer_sync(...same inputs adapted to sync callers...) -> RagOutcome: ...
```

## Why this is the narrowest viable cut

This design does not invent a new retriever, new prompt system, or new API
schema. It reuses:

- `retrieval_runtime` for document normalization, context bundles, KG helpers,
  and section normalization
- `policy` for refusal behavior
- `llm_runtime` for prompt artifacts, LLM request resolution, execution, and
  output validation

Only the orchestration order and result contract move into one place.

That is the smallest change that removes drift without rewriting the lower
layers that already work.

## Adapter responsibilities after extraction

### Pipeline adapter

`earCrawler/rag/pipeline.py` should become a thin sync wrapper around
`orchestrator.answer_sync(...)`.

It should keep:

- the current public function name `answer_with_rag(...)`
- the current dict-shaped return contract used by CLI/eval code
- optional audit emission, via an injected audit hook
- current strict-retrieval wrapper behavior until parity migration is complete

It should stop owning:

- prompt assembly logic
- policy evaluation logic
- direct LLM execution logic
- direct KG-expansion orchestration logic

### API adapter

`service/api_server/rag_service.py` should become an adapter module that:

- constructs the retrieval runner with cache + thread offload
- constructs the generate runner with thread offload
- calls `orchestrator.retrieve_only(...)` for `/v1/rag/query`
- calls `orchestrator.answer(...)` for `/v1/rag/answer`
- maps `RagOutcome` to `RagResponse` / `RagGeneratedResponse`
- keeps lineage building for `/v1/rag/query`
- keeps HTTP-specific status mapping

`service/api_server/routers/rag.py` should shrink to request parsing, dependency
injection, logging, and final response construction.

## Behavior decisions for implementation

The shared layer needs a few explicit policy knobs because current callers do
not behave identically.

### 1. Empty retrieval policy

Required parameter: `refuse_on_empty`

- API current behavior: `True`
- pipeline current behavior: `False`

Recommendation:

- keep `refuse_on_empty` explicit during the first extraction
- default the shared layer to `True`
- have the pipeline wrapper pass its current legacy value during migration
- add parity tests for the selected policy before removing the legacy pipeline
  path

This avoids a hidden behavior change while still making the difference
machine-visible.

### 2. KG expansion in the API path

Recommendation:

- shared layer supports KG expansion
- API adapter passes `kg_expansion=False` by default until capability-state work
  explicitly promotes it
- pipeline wrapper keeps its current env/task-driven behavior

This preserves the supported API boundary and avoids silently widening the
optional/quarantined feature surface.

### 3. Prompt context shape

Recommendation:

- canonical prompt contexts should come from
  `retrieval_runtime.build_retrieval_context_bundle(...)`
- API response display fields may keep current formatting if clients depend on
  it, but the prompt inputs used for policy and generation should be shared

This is the cleanest way to stop API/pipeline prompt drift.

### 4. Retrieval failure handling

Recommendation:

- shared retrieval returns structured failure state
- wrappers decide whether to raise, return `503`, or continue with warnings

The shared layer should not know about HTTP or Click exceptions.

## Concrete file changes recommended for step 6

Primary implementation files:

- add `earCrawler/rag/orchestrator.py`
- refactor `earCrawler/rag/pipeline.py` into a thin wrapper over the shared
  orchestrator
- refactor `service/api_server/rag_service.py` into adapter code only
- simplify `service/api_server/routers/rag.py` once orchestration moves out

Likely helper extractions:

- add a small retriever-state normalizer to `earCrawler/rag/retrieval_runtime.py`
  so both adapters compute `rag_enabled`, `retriever_ready`, `failure_type`,
  `disabled_reason`, `index_path`, and `model_name` the same way
- reuse `retrieval_runtime.build_retrieval_context_bundle(...)` as the canonical
  answer-context builder instead of maintaining API-only prompt-context logic

Tests to add or update:

- add a parity-focused test module such as
  `tests/rag/test_shared_orchestration_parity.py`
- keep `tests/service/test_rag_endpoint.py` for HTTP status + schema behavior
- keep `tests/rag/test_pipeline_strict_output.py`,
  `tests/rag/test_temporal_reasoning.py`, and
  `tests/rag/test_pipeline_kg_expansion.py` as wrapper-level regression tests

## Required parity cases

Step 6 should not be considered complete unless API and pipeline paths are
proven to agree on:

- temporal refusal decisions
- empty/thin retrieval refusal decisions for the same configured policy
- prompt redaction mode and egress-decision fields
- strict output validation results
- provider-disabled and provider-unavailable behavior
- KG expansion inclusion/exclusion for the same capability setting
- timing field population and retrieval-empty reasons

The parity tests should compare canonical `RagOutcome` values first. Adapter
tests should then separately verify HTTP status codes, API schema mapping, and
CLI/pipeline dict shaping.

## Migration risks

Highest-risk behavior changes:

- changing pipeline empty-retrieval behavior without updating eval assumptions
- accidentally enabling KG expansion on the API path by default
- changing API-visible `contexts` formatting if clients or tests depend on it
- breaking existing monkeypatch-heavy tests that currently patch
  `pipeline.answer_with_rag` or `service.api_server.routers.rag.generate_chat`

Mitigations:

- keep wrapper entry points stable
- keep adapter-specific response shaping stable
- add canonical parity tests before deleting existing wrapper tests
- migrate in two passes: shared core first, wrapper cleanup second

## Non-goals

This design does not:

- redesign retrieval backends
- change API request or response schemas
- graduate quarantined KG/search features
- introduce multi-instance cache/state support
- collapse lineage enrichment into the core RAG package

## Recommended implementation order

1. Add the shared `orchestrator.py` module with canonical request/result
   dataclasses and shared answer flow.
2. Switch `earCrawler/rag/pipeline.py` to the shared sync wrapper while keeping
   its current return dict.
3. Switch `service/api_server/rag_service.py` to shared retrieval/answer
   orchestration while preserving HTTP behavior.
4. Add parity tests comparing shared outcomes across pipeline and API adapters.
5. Remove any remaining duplicated prompt/policy/retrieval-empty logic from the
   wrappers.
