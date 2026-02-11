from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import unquote

from earCrawler.kg.iri import section_iri
from earCrawler.rag.corpus_contract import normalize_ear_doc_id, normalize_ear_section_id


_CANONICAL_SECTION_IRI_PREFIX = "https://ear.example.org/resource/ear/section/"
_CANONICAL_SECTION_IRI_RE = re.compile(
    r"https://ear\.example\.org/resource/ear/section/([A-Za-z0-9\-._~%]+)"
)
_LEGACY_SECTION_TOKEN_RE = re.compile(r"\bear:s_([A-Za-z0-9_]+)\b")


@dataclass(frozen=True)
class DatasetRefIssue:
    dataset_id: str
    file: str
    line: int
    field: str
    value: str
    message: str


def _resolve_file(base: Path, raw: str) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    if candidate.exists():
        return candidate.resolve()
    return (base / candidate).resolve()


def _dataset_is_v2(entry: Mapping[str, object]) -> bool:
    ds_id = str(entry.get("id") or "")
    if ds_id.endswith(".v2"):
        return True
    try:
        return int(entry.get("version") or 0) >= 2
    except Exception:
        return False


def _iter_jsonl(path: Path) -> Iterable[tuple[int, dict]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            yield line_no, json.loads(stripped)


def _normalize_required_section(
    *,
    raw: object,
    dataset_id: str,
    file_path: Path,
    line_no: int,
    field: str,
    issues: list[DatasetRefIssue],
) -> str | None:
    normalized = normalize_ear_section_id(raw)
    if normalized:
        return normalized
    issues.append(
        DatasetRefIssue(
            dataset_id=dataset_id,
            file=str(file_path),
            line=line_no,
            field=field,
            value=str(raw),
            message="cannot normalize to canonical EAR section id",
        )
    )
    return None


def _collect_item_sections(
    *,
    item: Mapping[str, object],
    dataset_id: str,
    file_path: Path,
    line_no: int,
    issues: list[DatasetRefIssue],
) -> set[str]:
    sections: set[str] = set()

    for sec in item.get("ear_sections") or []:
        normalized = _normalize_required_section(
            raw=sec,
            dataset_id=dataset_id,
            file_path=file_path,
            line_no=line_no,
            field="ear_sections",
            issues=issues,
        )
        if normalized:
            sections.add(normalized)

    expected = item.get("expected") or {}
    if isinstance(expected, Mapping):
        for sec in expected.get("citations") or []:
            normalized = _normalize_required_section(
                raw=sec,
                dataset_id=dataset_id,
                file_path=file_path,
                line_no=line_no,
                field="expected.citations",
                issues=issues,
            )
            if normalized:
                sections.add(normalized)

    evidence = item.get("evidence") or {}
    if isinstance(evidence, Mapping):
        for span in evidence.get("doc_spans") or []:
            if not isinstance(span, Mapping):
                continue
            span_raw = span.get("span_id")
            if span_raw not in (None, ""):
                normalized = _normalize_required_section(
                    raw=span_raw,
                    dataset_id=dataset_id,
                    file_path=file_path,
                    line_no=line_no,
                    field="evidence.doc_spans.span_id",
                    issues=issues,
                )
                if normalized:
                    sections.add(normalized)
            doc_raw = span.get("doc_id")
            if doc_raw not in (None, ""):
                doc_norm = normalize_ear_doc_id(doc_raw)
                if doc_norm is None:
                    issues.append(
                        DatasetRefIssue(
                            dataset_id=dataset_id,
                            file=str(file_path),
                            line=line_no,
                            field="evidence.doc_spans.doc_id",
                            value=str(doc_raw),
                            message="cannot normalize EAR doc_id",
                        )
                    )
    return sections


def _collect_dataset_sections(
    *,
    manifest_path: Path,
    manifest_obj: Mapping[str, object],
    dataset_id: str,
    only_v2: bool,
    dataset_id_pattern: str | None,
) -> tuple[list[dict[str, object]], list[DatasetRefIssue]]:
    entries = list(manifest_obj.get("datasets", []) or [])
    if dataset_id != "all":
        entries = [entry for entry in entries if str(entry.get("id") or "") == dataset_id]
    if only_v2:
        entries = [entry for entry in entries if _dataset_is_v2(entry)]
    if dataset_id_pattern:
        pattern = re.compile(dataset_id_pattern)
        entries = [
            entry for entry in entries if pattern.search(str(entry.get("id") or ""))
        ]
    if not entries:
        raise ValueError("No datasets matched selection (dataset_id/only-v2/pattern).")

    dataset_reports: list[dict[str, object]] = []
    issues: list[DatasetRefIssue] = []
    for entry in entries:
        ds_id = str(entry.get("id") or "")
        file_path = _resolve_file(manifest_path.parent, str(entry.get("file") or ""))
        if not file_path.exists():
            raise FileNotFoundError(f"Dataset file not found: {file_path}")

        sections: set[str] = set()
        item_count = 0
        for line_no, item in _iter_jsonl(file_path):
            item_count += 1
            sections.update(
                _collect_item_sections(
                    item=item,
                    dataset_id=ds_id,
                    file_path=file_path,
                    line_no=line_no,
                    issues=issues,
                )
            )

        dataset_reports.append(
            {
                "dataset_id": ds_id,
                "file": str(file_path),
                "num_items": item_count,
                "expected_sections": sorted(sections),
            }
        )

    return dataset_reports, issues


def _load_corpus_doc_counts(corpus_path: Path) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    with corpus_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in corpus at line {line_no}") from exc
            doc_norm = normalize_ear_doc_id(row.get("doc_id"))
            if doc_norm:
                counts[doc_norm] += 1
    return counts


def _legacy_token_to_section_id(token_body: str) -> str | None:
    tokens = [tok for tok in str(token_body).split("_") if tok]
    if len(tokens) < 2:
        return None
    if not (tokens[0].isdigit() and len(tokens[0]) == 3):
        return None
    if not tokens[1].isdigit():
        return None

    section_body = f"{tokens[0]}.{tokens[1]}"
    for tok in tokens[2:]:
        section_body += f"({tok.lower()})"
    return normalize_ear_section_id(section_body)


def _scan_kg_sections(kg_path: Path) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    canonical: dict[str, set[str]] = defaultdict(set)
    legacy: dict[str, set[str]] = defaultdict(set)
    with kg_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            for match in _CANONICAL_SECTION_IRI_RE.finditer(line):
                encoded = match.group(1)
                decoded = unquote(encoded)
                section_id = normalize_ear_section_id(decoded)
                if not section_id:
                    continue
                canonical[section_id].add(_CANONICAL_SECTION_IRI_PREFIX + encoded)
            for match in _LEGACY_SECTION_TOKEN_RE.finditer(line):
                section_id = _legacy_token_to_section_id(match.group(1))
                if not section_id:
                    continue
                legacy[section_id].add(match.group(0))
    return canonical, legacy


def _choose_kg_path(manifest_path: Path, explicit_kg_path: str | None) -> Path | None:
    if explicit_kg_path:
        resolved = _resolve_file(manifest_path.parent, explicit_kg_path)
        if not resolved.exists():
            raise FileNotFoundError(f"KG file not found: {resolved}")
        return resolved

    candidates = [
        Path("kg/canonical/dataset.nq"),
        Path("kg/baseline/dataset.nq"),
        Path("kg/ear_triples.ttl"),
        Path("kg/ear.ttl"),
    ]
    resolved_candidates = []
    for candidate in candidates:
        resolved = _resolve_file(manifest_path.parent, str(candidate))
        if resolved.exists():
            resolved_candidates.append(resolved)
    if not resolved_candidates:
        return None

    # Prefer non-empty files so placeholder manifests do not hide usable KG data.
    for candidate in resolved_candidates:
        if candidate.stat().st_size > 64:
            return candidate
    return resolved_candidates[0]


def _render_markdown(report: Mapping[str, object], max_list: int) -> str:
    summary = report.get("summary") or {}
    lines: list[str] = []
    lines.append("# Identifier consistency report")
    lines.append("")
    lines.append("## Inputs")
    lines.append(f"- manifest: `{report.get('manifest_path')}`")
    lines.append(f"- corpus: `{report.get('corpus_path')}`")
    lines.append(f"- kg_enabled: `{report.get('kg_enabled')}`")
    if report.get("kg_enabled"):
        lines.append(f"- kg_path: `{report.get('kg_path')}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- status: `{summary.get('status')}`")
    lines.append(f"- expected_sections: `{summary.get('expected_sections')}`")
    lines.append(f"- ok: `{summary.get('ok')}`")
    lines.append(f"- missing_in_corpus: `{summary.get('missing_in_corpus')}`")
    lines.append(f"- duplicate_in_corpus: `{summary.get('duplicate_in_corpus')}`")
    if report.get("kg_enabled"):
        lines.append(f"- missing_in_kg: `{summary.get('missing_in_kg')}`")
        lines.append(f"- duplicate_in_kg: `{summary.get('duplicate_in_kg')}`")
        lines.append(f"- noncanonical_in_kg: `{summary.get('noncanonical_in_kg')}`")
    lines.append(f"- invalid_dataset_refs: `{summary.get('invalid_dataset_refs')}`")

    for key in (
        "missing_corpus_sections",
        "duplicate_corpus_sections",
        "missing_kg_sections",
        "duplicate_kg_sections",
        "noncanonical_kg_sections",
    ):
        values = report.get(key) or []
        if not values:
            continue
        lines.append("")
        lines.append(f"## {key}")
        for value in list(values)[:max_list]:
            lines.append(f"- `{value}`")

    invalid = report.get("invalid_dataset_ref_examples") or []
    if invalid:
        lines.append("")
        lines.append("## Invalid dataset reference examples")
        for row in list(invalid)[:max_list]:
            lines.append(
                "- `{dataset_id}` line `{line}` `{field}` value `{value}`: {message}".format(
                    dataset_id=row.get("dataset_id"),
                    line=row.get("line"),
                    field=row.get("field"),
                    value=row.get("value"),
                    message=row.get("message"),
                )
            )
    return "\n".join(lines) + "\n"


def run_check(
    *,
    manifest_path: Path,
    corpus_path: Path,
    dataset_id: str,
    only_v2: bool,
    dataset_id_pattern: str | None,
    kg_enabled: bool,
    explicit_kg_path: str | None,
) -> dict[str, object]:
    manifest_obj = json.loads(manifest_path.read_text(encoding="utf-8"))
    datasets, ref_issues = _collect_dataset_sections(
        manifest_path=manifest_path,
        manifest_obj=manifest_obj,
        dataset_id=dataset_id,
        only_v2=only_v2,
        dataset_id_pattern=dataset_id_pattern,
    )
    expected_sections = sorted(
        {sec for dataset in datasets for sec in dataset.get("expected_sections", [])}
    )
    corpus_doc_counts = _load_corpus_doc_counts(corpus_path)

    missing_corpus: list[str] = []
    duplicate_corpus: list[str] = []
    for sec in expected_sections:
        count = int(corpus_doc_counts.get(sec, 0))
        if count == 0:
            missing_corpus.append(sec)
        elif count > 1:
            duplicate_corpus.append(sec)

    selected_kg_path: Path | None = None
    kg_canonical: dict[str, set[str]] = {}
    kg_legacy: dict[str, set[str]] = {}
    if kg_enabled:
        selected_kg_path = _choose_kg_path(manifest_path, explicit_kg_path)
        if selected_kg_path is None:
            raise FileNotFoundError(
                "KG checking is enabled but no KG file was found. Provide --kg-path."
            )
        kg_canonical, kg_legacy = _scan_kg_sections(selected_kg_path)

    missing_kg: list[str] = []
    duplicate_kg: list[str] = []
    noncanonical_kg: list[str] = []
    for sec in expected_sections:
        if not kg_enabled:
            continue
        expected_iri = section_iri(sec)
        canonical_hits = kg_canonical.get(sec, set())
        if not canonical_hits:
            if kg_legacy.get(sec):
                noncanonical_kg.append(sec)
            else:
                missing_kg.append(sec)
            continue
        if len(canonical_hits) > 1:
            duplicate_kg.append(sec)
            continue
        if expected_iri not in canonical_hits:
            noncanonical_kg.append(sec)

    status = "ok"
    if (
        missing_corpus
        or duplicate_corpus
        or missing_kg
        or duplicate_kg
        or noncanonical_kg
        or ref_issues
    ):
        status = "fail"

    ok_count = len(expected_sections)
    ok_count -= len(set(missing_corpus))
    ok_count -= len(set(duplicate_corpus))
    if kg_enabled:
        ok_count -= len(set(missing_kg))
        ok_count -= len(set(duplicate_kg))
        ok_count -= len(set(noncanonical_kg))
    ok_count = max(0, ok_count)

    report = {
        "manifest_path": str(manifest_path),
        "corpus_path": str(corpus_path),
        "kg_enabled": bool(kg_enabled),
        "kg_path": str(selected_kg_path) if selected_kg_path else None,
        "dataset_selector": {
            "dataset_id": dataset_id,
            "only_v2": bool(only_v2),
            "dataset_id_pattern": dataset_id_pattern,
        },
        "datasets": datasets,
        "summary": {
            "status": status,
            "num_datasets": len(datasets),
            "expected_sections": len(expected_sections),
            "ok": ok_count,
            "missing_in_corpus": len(missing_corpus),
            "duplicate_in_corpus": len(duplicate_corpus),
            "missing_in_kg": len(missing_kg) if kg_enabled else 0,
            "duplicate_in_kg": len(duplicate_kg) if kg_enabled else 0,
            "noncanonical_in_kg": len(noncanonical_kg) if kg_enabled else 0,
            "invalid_dataset_refs": len(ref_issues),
        },
        "missing_corpus_sections": sorted(missing_corpus),
        "duplicate_corpus_sections": sorted(duplicate_corpus),
        "missing_kg_sections": sorted(missing_kg),
        "duplicate_kg_sections": sorted(duplicate_kg),
        "noncanonical_kg_sections": sorted(noncanonical_kg),
        "invalid_dataset_ref_examples": [
            {
                "dataset_id": issue.dataset_id,
                "file": issue.file,
                "line": issue.line,
                "field": issue.field,
                "value": issue.value,
                "message": issue.message,
            }
            for issue in ref_issues[:100]
        ],
    }
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check consistency of expected section IDs across eval datasets, corpus, and KG."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("eval") / "manifest.json",
        help="Eval manifest path.",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("data") / "faiss" / "retrieval_corpus.jsonl",
        help="Retrieval corpus JSONL path used for exact section lookup.",
    )
    parser.add_argument(
        "--dataset-id",
        default="all",
        help="Specific dataset id to check, or 'all'.",
    )
    parser.add_argument(
        "--only-v2",
        action="store_true",
        default=True,
        help="Restrict to v2 datasets (default: on).",
    )
    parser.add_argument(
        "--include-all-versions",
        action="store_true",
        help="Disable v2-only filtering.",
    )
    parser.add_argument(
        "--dataset-id-pattern",
        default=None,
        help="Optional regex filter for dataset ids.",
    )
    parser.add_argument(
        "--kg-path",
        default=None,
        help="Optional KG triples file (NQ/TTL/NT) to validate section IRI presence.",
    )
    parser.add_argument(
        "--disable-kg",
        action="store_true",
        help="Skip KG checks and only validate dataset IDs against corpus.",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("dist") / "eval" / "id_consistency_report.json",
        help="Output path for machine-readable report.",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=Path("dist") / "eval" / "id_consistency_report.md",
        help="Output path for markdown summary report.",
    )
    parser.add_argument(
        "--max-list",
        type=int,
        default=30,
        help="Max list entries to include in markdown sections.",
    )

    args = parser.parse_args(argv)

    manifest_path = args.manifest.resolve()
    corpus_path = args.corpus.resolve()
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus not found: {corpus_path}")

    only_v2 = bool(args.only_v2 and not args.include_all_versions)
    kg_enabled = not bool(args.disable_kg)

    report = run_check(
        manifest_path=manifest_path,
        corpus_path=corpus_path,
        dataset_id=str(args.dataset_id),
        only_v2=only_v2,
        dataset_id_pattern=args.dataset_id_pattern,
        kg_enabled=kg_enabled,
        explicit_kg_path=args.kg_path,
    )

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.out_md.write_text(_render_markdown(report, args.max_list), encoding="utf-8")

    summary = report.get("summary") or {}
    print(json.dumps(summary, sort_keys=True))
    print(f"Wrote: {args.out_json}")
    print(f"Wrote: {args.out_md}")

    if str(summary.get("status") or "fail") != "ok":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

