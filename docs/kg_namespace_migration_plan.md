# One-time KG namespace migration plan

This plan describes how to migrate legacy IRIs/namespaces to the canonical `ear.example.org` namespaces with deterministic, idempotent tooling while preserving backward compatibility.

## Inventory (what exists today)

Namespaces currently found in-repo include:

- Canonical namespaces already used by SPARQL templates and pipelines:
  - `https://ear.example.org/schema#`
  - `https://ear.example.org/entity/`
  - `https://ear.example.org/part/`
  - `https://ear.example.org/anchor/`
  - `https://ear.example.org/policyHint/`
  - `https://ear.example.org/graph/…` (e.g. `https://ear.example.org/graph/main`)
- Legacy namespaces present in older KG TTL/NQ fixtures and dataset references:
  - `https://example.org/ear#`
  - `https://example.org/entity#`
  - `http://example.org/ear/`

## Chosen canonical base + rationale

- Canonical domain is `ear.example.org` because it is already used consistently across:
  - `earCrawler/sparql/*.sparql`
  - loaders/pipelines that emit entities/parts
  - service configuration defaults (graph IRIs)
- Canonicalization splits **schema terms** (under `…/schema#`) from **resource nodes** (under `…/resource/…`) to make grounding/citation alignment explicit and to avoid conflating terms with instances.

## Migration phases (recommended order)

### Phase 1 — Introduce canonical constants + IRI builders

- Add canonical namespace constants:
  - `earCrawler/kg/namespaces.py`
- Add deterministic IRI builders:
  - `earCrawler/kg/iri.py`
- Update KG emitters and provenance minting to use the helpers so new outputs are canonical.

### Phase 2 — Add legacy alias mapping (backward compatible reads)

Goal: old snapshots can still be consumed without forcing an immediate rebuild.

- Provide a best-effort canonicalizer:
  - `earCrawler.kg.iri.canonicalize_iri(iri: str) -> str`
- Consumers that compare IRIs for grounding/citation SHOULD canonicalize inputs before comparison.

### Phase 3 — Migrate stored RDF artifacts (TTL/NT/NQ)

For any stored artifacts containing legacy IRIs, rewrite to canonical IRIs deterministically.

Tooling:

- `scripts/kg/migrate_namespaces.py` parses RDF and rewrites all `URIRef` terms via `canonicalize_iri`, then writes sorted output.

Recommended approach:

1. Write migrated files to a new directory.
2. Validate consumers/tests against the migrated outputs.
3. Swap the migrated artifacts into place.

### Phase 4 — Migrate SPARQL templates (if any legacy namespaces exist)

Most templates already use canonical prefixes. If legacy namespaces exist in any `.sparql`/`.rq` templates, rewrite them using the same tool with `--from/--to` pairs.

### Phase 5 — Migrate evaluation dataset references + validate

Update:

- `eval/manifest.json` curated reference lists (`references.kg_nodes`)
- `eval/*.jsonl` evidence and entity references (`kg_entities`, `evidence.kg_nodes`)
- Any other curated reference maps used for grounding/citation alignment (e.g. `data/kg_expansion.json`)

Then run:

- `python eval/validate_datasets.py`
- `py -m pytest -q tests/eval`

### Phase 6 — Freeze and remove legacy writers (later)

After downstream tooling no longer depends on legacy IRIs:

- Remove any code paths that emit legacy IRIs.
- Tighten validation to fail fast if legacy namespaces reappear in new outputs.

## One-time migration command lines

### Migrate eval references in place (safe + idempotent)

```powershell
py scripts/kg/migrate_namespaces.py --in-place "eval/*.json" "eval/*.jsonl" "data/kg_expansion.json"
```

Idempotency guarantee:

- Running the same command multiple times MUST result in `changed 0 file(s)` after the first successful migration.

### Migrate RDF artifacts to a new directory (recommended)

```powershell
py scripts/kg/migrate_namespaces.py --out-dir dist/migrated_kg "kg/**/*.ttl" "kg/**/*.nq" "kg/**/*.nt"
```

After validating, copy/swap the migrated files into their canonical locations.

## Determinism and non-breaking behavior

- The migrator writes RDF outputs in a deterministic sorted order.
- JSON/JSONL rewrites are limited to known reference keys (`kg_entities`, `kg_nodes`, `kg_paths`, `label_hints`) and MUST NOT rewrite arbitrary free text.
- Backward compatibility is preserved via explicit canonicalization (`canonicalize_iri`) so legacy IRIs in stored snapshots can still be recognized without breaking existing tooling.

