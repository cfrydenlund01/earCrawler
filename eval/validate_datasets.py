from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, Sequence, Set, Tuple, Any

from jsonschema import Draft7Validator


@dataclass(frozen=True)
class ValidationIssue:
    dataset_id: str
    file: Path
    line: int
    message: str
    instance_path: str


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_schema(schema_path: Path) -> Draft7Validator:
    schema = _load_json(schema_path)
    return Draft7Validator(schema)


def _resolve_dataset_file(manifest_path: Path, entry_file: str) -> Path:
    candidate = Path(entry_file)
    if candidate.is_absolute():
        return candidate
    if candidate.exists():
        return candidate
    return (manifest_path.parent / candidate).resolve()


def _load_references(manifest: dict) -> Tuple[Dict[str, Set[str]], Set[str], Set[str]]:
    references = manifest.get("references", {}) or {}
    sections_map: Dict[str, Set[str]] = {}
    for doc_id, spans in (references.get("sections", {}) or {}).items():
        sections_map[doc_id] = {str(value) for value in spans or []}
    kg_nodes = {str(value) for value in (references.get("kg_nodes") or [])}
    kg_paths = {str(value) for value in (references.get("kg_paths") or [])}
    return sections_map, kg_nodes, kg_paths


def _iter_dataset_entries(
    manifest: dict,
    manifest_path: Path,
    dataset_ids: Sequence[str] | None,
) -> Iterator[tuple[str, Path]]:
    datasets = manifest.get("datasets", [])
    selected = set(dataset_ids) if dataset_ids else None
    for entry in datasets:
        dataset_id = entry.get("id")
        if not dataset_id:
            continue
        if selected and dataset_id not in selected:
            continue
        file_path = _resolve_dataset_file(manifest_path, str(entry.get("file", "")))
        yield dataset_id, file_path


def _iter_items(path: Path) -> Iterator[tuple[int, dict]]:
    with path.open("r", encoding="utf-8") as handle:
        for idx, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            obj = json.loads(stripped)
            yield idx, obj


def _validate_doc_spans(
    *,
    dataset_id: str,
    file_path: Path,
    line_no: int,
    evidence: dict,
    section_map: Dict[str, Set[str]],
) -> Iterator[ValidationIssue]:
    for span in evidence.get("doc_spans", []):
        doc_id = str(span.get("doc_id") or "")
        span_id = str(span.get("span_id") or "")
        if not doc_id or not span_id:
            continue
        allowed = section_map.get(doc_id)
        if not allowed:
            yield ValidationIssue(
                dataset_id=dataset_id,
                file=file_path,
                line=line_no,
                message=f"doc_id '{doc_id}' not registered in manifest references",
                instance_path="evidence/doc_spans",
            )
        elif span_id not in allowed:
            yield ValidationIssue(
                dataset_id=dataset_id,
                file=file_path,
                line=line_no,
                message=f"span_id '{span_id}' missing from manifest for doc_id '{doc_id}'",
                instance_path="evidence/doc_spans",
            )


def _validate_kg_refs(
    *,
    dataset_id: str,
    file_path: Path,
    line_no: int,
    evidence: dict,
    kg_nodes: Set[str],
    kg_paths: Set[str],
) -> Iterator[ValidationIssue]:
    if kg_nodes:
        for node in evidence.get("kg_nodes", []):
            node_str = str(node or "")
            if node_str and node_str not in kg_nodes:
                yield ValidationIssue(
                    dataset_id=dataset_id,
                    file=file_path,
                    line=line_no,
                    message=f"kg_node '{node_str}' not registered in manifest references",
                    instance_path="evidence/kg_nodes",
                )
    if kg_paths:
        for path in evidence.get("kg_paths", []):
            path_str = str(path or "")
            if path_str and path_str not in kg_paths:
                yield ValidationIssue(
                    dataset_id=dataset_id,
                    file=file_path,
                    line=line_no,
                    message=f"kg_path '{path_str}' not registered in manifest references",
                    instance_path="evidence/kg_paths",
                )


def validate_datasets(
    manifest_path: Path | None = None,
    schema_path: Path | None = None,
    dataset_ids: Sequence[str] | None = None,
) -> list[ValidationIssue]:
    manifest_path = (manifest_path or Path("eval") / "manifest.json").resolve()
    schema_path = (schema_path or Path("eval") / "schema.json").resolve()

    manifest = _load_json(manifest_path)
    validator = _load_schema(schema_path)
    section_map, kg_nodes, kg_paths = _load_references(manifest)

    issues: list[ValidationIssue] = []
    for dataset_id, file_path in _iter_dataset_entries(
        manifest, manifest_path, dataset_ids
    ):
        if not file_path.exists():
            issues.append(
                ValidationIssue(
                    dataset_id=dataset_id,
                    file=file_path,
                    line=0,
                    message="dataset file not found",
                    instance_path="",
                )
            )
            continue
        for line_no, item in _iter_items(file_path):
            for error in validator.iter_errors(item):
                issues.append(
                    ValidationIssue(
                        dataset_id=dataset_id,
                        file=file_path,
                        line=line_no,
                        message=error.message,
                        instance_path="/".join(str(p) for p in error.path),
                    )
                )
            evidence: dict[str, Any] = item.get("evidence", {}) or {}
            issues.extend(
                _validate_doc_spans(
                    dataset_id=dataset_id,
                    file_path=file_path,
                    line_no=line_no,
                    evidence=evidence,
                    section_map=section_map,
                )
            )
            issues.extend(
                _validate_kg_refs(
                    dataset_id=dataset_id,
                    file_path=file_path,
                    line_no=line_no,
                    evidence=evidence,
                    kg_nodes=kg_nodes,
                    kg_paths=kg_paths,
                )
            )
    return issues


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate evaluation datasets against schema."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("eval") / "manifest.json",
        help="Path to eval manifest JSON.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("eval") / "schema.json",
        help="Path to JSON Schema file.",
    )
    parser.add_argument(
        "--dataset-id",
        action="append",
        dest="dataset_ids",
        help="Restrict validation to one or more dataset IDs (repeatable).",
    )
    args = parser.parse_args(argv)

    issues = validate_datasets(args.manifest, args.schema, args.dataset_ids or None)
    if issues:
        print(f"Validation failed for {len(issues)} issue(s):")
        for issue in issues:
            print(
                f"- {issue.dataset_id} @ {issue.file} line {issue.line}: "
                f"{issue.message} (path={issue.instance_path or '/'})"
            )
        return 1
    print("All evaluation datasets validated successfully.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
