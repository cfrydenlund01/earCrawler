# Corpus Identity ADR

Prepared: March 6, 2026

## Problem

The curated corpus pipeline in `earCrawler/corpus/builder.py` previously used the
paragraph text hash as the effective record identity. That collapsed distinct
records whenever two sources or sections carried identical text. The immediate
failure mode was that one source record disappeared from the corpus, and the
same collapse then propagated into KG paragraph IRIs because emitters also used
the content hash as the paragraph node identity.

This broke lineage: identical text no longer implied distinct provenance.

## Decision

Use a source-aware identity scheme for curated corpus records:

- Canonical corpus record id: `"<source>:<identifier>"`
- Source-local stable identifier: stored in `identifier`
- Content fingerprint: stored in `content_sha256`
- Backward-compatible alias: `sha256` remains the content fingerprint, but it is
  no longer treated as the record identity

Examples:

- EAR paragraph `EAR-001:0` becomes corpus record id `ear:EAR-001:0`
- NSF paragraph `NSF-001:0` becomes corpus record id `nsf:NSF-001:0`

The canonical section citation rules in `docs/identifier_policy.md` do not
change. This ADR only changes corpus record identity and paragraph provenance,
not canonical EAR citation ids.

## KG impact

KG paragraph IRIs now derive from the source-aware corpus record id when that
id is available. Hash-only paragraph IRIs remain supported as a legacy fallback
for old fixtures and transitional artifacts.

Result:

- two records with identical text now produce two paragraph nodes
- `prov:wasDerivedFrom` carries the source-aware record id
- `dct:identifier` preserves the source-local identifier

## Eval impact

Evaluation evidence resolution now prefers the source-aware `record_id` when
showing matched corpus records, but section-based evidence matching is
unchanged.

## Migration

Generated artifacts must be rebuilt rather than hand-edited:

1. Re-run `py -m earCrawler.cli corpus build ...` to rewrite `*_corpus.jsonl`
   with canonical source-aware ids and `content_sha256`.
2. Re-run KG emission/loading so paragraph IRIs are rebuilt from corpus record
   identity instead of content hash.
3. Rebuild any downstream snapshots or bundles that embedded the old paragraph
   IRIs.

No citation dataset changes are required because canonical section ids remain
unchanged.
