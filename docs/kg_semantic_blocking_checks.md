# KG Semantic Blocking Checks

Prepared: March 11, 2026

## Purpose

Define the minimum SPARQL sanity checks that are release-blocking for the supported CI evidence path, in addition to SHACL.

This policy is intentionally narrow. It blocks defects with the highest supported-path risk while avoiding broad speculative gating.

## Blocking checks for the supported gate

The supported CI gate runs:

```powershell
py -m cli.kg_validate --fail-on supported `
  --blocking-check orphan_paragraphs `
  --blocking-check entity_mentions_without_type
```

Blocking checks:

- `orphan_paragraphs`
  - Why blocking: a paragraph disconnected from section lineage is a core KG integrity failure for the supported read/query path.
  - Risk addressed: semantically incomplete lineage can pass structural checks and degrade downstream retrieval and reasoning.

- `entity_mentions_without_type`
  - Why blocking: entity nodes that appear in triples but are missing `ear:Entity` type are malformed graph state and can break entity-level behavior.
  - Risk addressed: malformed entity data can evade class-targeted validation and silently reduce graph quality.

## Non-blocking checks for now

All other SPARQL sanity checks remain reported but non-blocking in the supported CI gate until there is current evidence they should be promoted without destabilizing the baseline path.

Current non-blocking set:

- `orphan_sections`
- `missing_provenance`
- `dangling_citations`

## Exemptions and overrides

`cli.kg_validate` supports explicit check override via repeatable `--blocking-check`.

Rules:

- CI should keep the default supported blocking set above unless a documented decision updates this file.
- Temporary narrowing for local investigation is allowed, but release CI changes require rationale in docs plus associated test updates.
- Unknown check names are rejected with usage error to prevent silent misconfiguration.
