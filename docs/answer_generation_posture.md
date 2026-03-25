# Supported Answer-Generation Posture

Status: active production-beta posture for generated answers as of March 25,
2026.

Use this document together with:

- `docs/Archive/RunPass11.md`
- `README.md`
- `RUNBOOK.md`
- `docs/capability_graduation_boundaries.md`
- `docs/local_adapter_release_evidence.md`
- `docs/model_training_surface_adr.md`

## Decision

For the supported Windows single-host production-beta target, EarCrawler
supports retrieval of grounded regulatory evidence. It does not support
autonomous legal or regulatory determinations by a generated-answer model.

`/v1/rag/answer` remains an `Optional` operator-controlled capability. When it
is enabled, generated output is supported only as a citation-grounded advisory
draft that must fail closed to `unanswerable` when the evidence is thin,
ambiguous, temporally inconsistent, or schema-invalid.

## Supported path

The supported production-beta answer path is:

- `Supported`: `/v1/rag/query` as the baseline retrieval surface for grounded
  evidence collection.
- `Optional`: `/v1/rag/answer` only as a draft answering aid that stays behind
  explicit runtime gates and does not widen the baseline support claim.

When `/v1/rag/answer` is enabled, the generated answer posture is limited to all
of the following:

- the output is grounded only in retrieved EAR text supplied to the model
- at least one citation quote must be a verbatim substring of the retrieved
  context for non-`unanswerable` answers
- strict JSON validation must succeed
- unsupported assumptions must force `unanswerable`
- thin, empty, or temporally ambiguous evidence must force abstention rather
  than guesswork

This means the supported behavior is "draft a grounded summary of retrieved
evidence or abstain." It does not mean "issue a reliable legal conclusion."

## Unsupported path

The following are not supported for the production-beta claim:

- autonomous legal interpretation
- autonomous export-license determinations
- customer-facing or operationally final legal/regulatory advice without human
  review
- model output that is not backed by grounded citations from retrieved evidence
- any local-adapter promotion claim based only on source presence or a partial
  evidence bundle
- any claim that a generated-answer path is baseline, default-on, or required
  for the supported operator workflow

## Abstention rules

The runtime must abstain with `label=unanswerable` when any of the following are
true:

- no retrieved evidence supports the question
- retrieval is explicitly configured to refuse on thin evidence and the minimum
  doc, score, or context thresholds are not met
- temporal applicability is ambiguous, conflicting, or unsupported by the
  retrieved evidence
- the generated output fails strict schema validation
- citations are not grounded in the retrieved context
- assumptions needed for the answer are not directly supported by the retrieved
  context

In production-beta terms, abstention is a required safety behavior, not a
degraded optional feature.

## Evidence threshold

No model path should be described as supportable beyond the advisory posture
above unless it has named, machine-checkable evidence.

Current threshold for any promotable local model path:

- pass the evidence contract in `docs/local_adapter_release_evidence.md`
- pass the benchmark thresholds in
  `config/local_adapter_release_evidence.example.json`
- produce a reviewable candidate outcome of
  `ready_for_formal_promotion_review`
- record a dated promotion decision that updates the capability registry and
  operator docs

Current repository evidence does not satisfy that threshold. The reviewed local
candidate bundle under
`dist/training/step52-real-candidate-gpt2b-20260319/` was validated on March
19, 2026 as `keep_optional` / `not_reviewable`, and its paired benchmark bundle
under `dist/benchmarks/step52-real-candidate-gpt2b-20260319/` shows zero answer
accuracy plus strict-output failures.

The repo also does not currently carry an equivalent promotion contract proving
that a remote-provider generated-answer path is release-ready for high-stakes
regulatory use. Remote providers therefore remain optional runtime integrations,
not a production-beta legal-answer guarantee.

## Human-review boundary

Human review is required before relying on generated output for any higher-risk
interpretation, including:

- whether a license is required in a real-world transaction
- whether a License Exception applies to a concrete fact pattern
- time-sensitive applicability when regulatory dates or revisions matter
- end-use, end-user, destination, or ECCN-sensitive conclusions with material
  compliance consequences
- any answer that will be communicated externally as advice or used as a final
  operational decision

If the needed human review is not available, the safe posture is to use
retrieval output only or abstain.

## Decision summary

- `Supported`: grounded evidence retrieval through `/v1/rag/query`
- `Optional`: `/v1/rag/answer` as an operator-controlled advisory draft path
  with mandatory abstention behavior
- `Unsupported`: autonomous legal/regulatory answering or any final-decision use
  without human review
- `Blocked from promotion today`: local-adapter serving beyond `Optional`,
  because the current evidence bundle is not reviewable
