from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

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


def validate_datasets(
    manifest_path: Path | None = None,
    schema_path: Path | None = None,
    dataset_ids: Sequence[str] | None = None,
) -> list[ValidationIssue]:
    manifest_path = (manifest_path or Path("eval") / "manifest.json").resolve()
    schema_path = (schema_path or Path("eval") / "schema.json").resolve()

    manifest = _load_json(manifest_path)
    validator = _load_schema(schema_path)

    issues: list[ValidationIssue] = []
    for dataset_id, file_path in _iter_dataset_entries(manifest, manifest_path, dataset_ids):
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
    return issues


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate evaluation datasets against schema.")
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
