from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from scripts.eval import validate_local_adapter_release_bundle as validator


SUMMARY_VERSION = "local-adapter-review-bundle.v1"
REVIEWABLE_DECISIONS = {
    "reject_candidate",
    "ready_for_formal_promotion_review",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_name(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "unknown"
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)).strip("._-") or "unknown"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def _bundle_rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _link_or_copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path) -> None:
    for path in _iter_files(src):
        _link_or_copy_file(path, dst / path.relative_to(src))


def _copy_path(src: Path, dst: Path) -> None:
    if src.is_dir():
        _copy_tree(src, dst)
        return
    _link_or_copy_file(src, dst)


def _default_bundle_id(run_dir: Path, benchmark_root: Path) -> str:
    run_short = _safe_name(run_dir.name)[:32].rstrip("._-") or "run"
    benchmark_short = _safe_name(benchmark_root.name)[:24].rstrip("._-") or "benchmark"
    seed = f"{run_dir.name}::{benchmark_root.name}"
    seed_hash = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10]
    return _safe_name(
        f"local_adapter_candidate_{run_short}_{benchmark_short}_{seed_hash}"
    )


def _bounded_bundle_id(value: str, *, max_chars: int = 120) -> str:
    safe = _safe_name(value)
    if len(safe) <= max_chars:
        return safe
    suffix = hashlib.sha256(safe.encode("utf-8")).hexdigest()[:10]
    prefix = safe[: max_chars - (len(suffix) + 1)].rstrip("._-") or "bundle"
    return f"{prefix}_{suffix}"


def _collect_bundle_files(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in _iter_files(root):
        records.append(
            {
                "path": _bundle_rel(path, root),
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return records


def _record_source_file(
    *,
    src: Path,
    dst: Path,
    bundle_root: Path,
    records: list[dict[str, Any]],
) -> None:
    records.append(
        {
            "source_path": str(src.resolve()),
            "bundle_path": _bundle_rel(dst, bundle_root),
            "sha256": _sha256_file(src),
            "size_bytes": src.stat().st_size,
        }
    )


def _record_source_path(
    *,
    src: Path,
    dst: Path,
    bundle_root: Path,
    records: list[dict[str, Any]],
) -> None:
    if src.is_dir():
        for path in _iter_files(src):
            _record_source_file(
                src=path,
                dst=dst / path.relative_to(src),
                bundle_root=bundle_root,
                records=records,
            )
        return
    _record_source_file(src=src, dst=dst, bundle_root=bundle_root, records=records)


def _validate_reviewable_bundle(
    *,
    run_dir: Path,
    benchmark_summary: Path,
    smoke_report: Path,
    contract: Path,
) -> dict[str, Any]:
    out_path = run_dir / "release_evidence_manifest.json"
    validator.main(
        [
            "--run-dir",
            str(run_dir),
            "--benchmark-summary",
            str(benchmark_summary),
            "--smoke-report",
            str(smoke_report),
            "--contract",
            str(contract),
            "--out",
            str(out_path),
        ]
    )
    if not out_path.exists():
        raise ValueError(
            "Release evidence validation did not produce release_evidence_manifest.json."
        )
    payload = _read_json(out_path)
    decision = str(payload.get("decision") or "").strip()
    if decision not in REVIEWABLE_DECISIONS:
        raise ValueError(
            "Candidate package is not reviewable yet: release evidence decision "
            f"is {decision or 'missing'}."
        )
    return payload


def _write_readme(
    *,
    path: Path,
    bundle_id: str,
    release_payload: dict[str, Any],
) -> None:
    training_run = release_payload.get("training_run") or {}
    benchmark = release_payload.get("benchmark") or {}
    lines = [
        "# Local Adapter Candidate Bundle",
        "",
        f"- Bundle id: `{bundle_id}`",
        f"- Created (UTC): `{_utc_now_iso()}`",
        f"- Release evidence decision: `{release_payload.get('decision')}`",
        f"- Candidate review status: `{release_payload.get('candidate_review_status')}`",
        f"- Evidence status: `{release_payload.get('evidence_status')}`",
        f"- Training run: `{training_run.get('run_dir')}`",
        f"- Benchmark bundle: `{benchmark.get('root')}`",
        "",
        "This bundle is a review package for the optional local-adapter path.",
        "It does not change the supported baseline by itself.",
        "",
        "Included directories:",
        "- `training/` Task 5.3 run artifacts plus adapter payload",
        "- `benchmark/` benchmark manifest, summary, artifacts, and preconditions",
        "- `runtime/` reviewed local-adapter smoke report",
        "- `docs/rollback/` named rollback references from the evidence contract",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assemble a reviewable local-adapter candidate bundle from an evidence-complete training run."
    )
    parser.add_argument("--run-dir", type=Path, required=True, help="Task 5.3 run directory (dist/training/<run_id>).")
    parser.add_argument("--benchmark-summary", type=Path, required=True, help="benchmark_summary.json from run_local_adapter_benchmark.py.")
    parser.add_argument("--smoke-report", type=Path, default=Path("kg") / "reports" / "local-adapter-smoke.json")
    parser.add_argument("--contract", type=Path, default=validator.DEFAULT_CONTRACT)
    parser.add_argument("--out-root", type=Path, default=Path("dist") / "reviewable_candidates")
    parser.add_argument("--bundle-id", default=None, help="Optional deterministic bundle id override.")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    run_dir = args.run_dir.resolve()
    benchmark_summary = args.benchmark_summary.resolve()
    smoke_report = args.smoke_report.resolve()
    contract = args.contract.resolve()
    benchmark_root = benchmark_summary.parent
    if not benchmark_summary.exists():
        print(f"Failed: benchmark summary not found: {benchmark_summary}")
        return 1
    if not smoke_report.exists():
        print(f"Failed: smoke report not found: {smoke_report}")
        return 1

    try:
        release_payload = _validate_reviewable_bundle(
            run_dir=run_dir,
            benchmark_summary=benchmark_summary,
            smoke_report=smoke_report,
            contract=contract,
        )
    except Exception as exc:
        print(f"Failed: {exc}")
        return 1

    bundle_id = _bounded_bundle_id(
        args.bundle_id or _default_bundle_id(run_dir, benchmark_root)
    )
    bundle_root = (args.out_root / bundle_id).resolve()
    if bundle_root.exists() and not args.overwrite:
        print(f"Failed: output directory exists: {bundle_root}. Use --overwrite.")
        return 1
    if bundle_root.exists() and args.overwrite:
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)

    copied_sources: list[dict[str, Any]] = []
    copy_plan = [
        (run_dir / "manifest.json", bundle_root / "training" / "manifest.json"),
        (run_dir / "run_config.json", bundle_root / "training" / "run_config.json"),
        (run_dir / "run_metadata.json", bundle_root / "training" / "run_metadata.json"),
        (run_dir / "inference_smoke.json", bundle_root / "training" / "inference_smoke.json"),
        (
            run_dir / "release_evidence_manifest.json",
            bundle_root / "training" / "release_evidence_manifest.json",
        ),
        (run_dir / "adapter", bundle_root / "training" / "adapter"),
        (benchmark_root, bundle_root / "benchmark"),
        (smoke_report, bundle_root / "runtime" / "local-adapter-smoke.json"),
    ]
    rollback_docs = release_payload.get("rollback_docs") or {}
    resolved_rollback = rollback_docs.get("resolved") or {}
    for path in resolved_rollback.values():
        copy_plan.append(
            (Path(str(path)).resolve(), bundle_root / "docs" / "rollback" / Path(str(path)).name)
        )

    try:
        for src, dst in copy_plan:
            if not src.exists():
                raise ValueError(f"Required bundle input is missing: {src}")
            _copy_path(src, dst)
            _record_source_path(
                src=src,
                dst=dst,
                bundle_root=bundle_root,
                records=copied_sources,
            )
    except Exception as exc:
        print(f"Failed: unable to assemble candidate bundle: {exc}")
        return 1

    readme_path = bundle_root / "README.md"
    _write_readme(
        path=readme_path,
        bundle_id=bundle_id,
        release_payload=release_payload,
    )

    bundle_manifest = {
        "schema_version": SUMMARY_VERSION,
        "bundle_id": bundle_id,
        "created_at_utc": _utc_now_iso(),
        "contract_path": str(contract),
        "reviewable": True,
        "decision": release_payload.get("decision"),
        "candidate_review_status": release_payload.get("candidate_review_status"),
        "evidence_status": release_payload.get("evidence_status"),
        "training_run": release_payload.get("training_run"),
        "runtime_smoke": release_payload.get("runtime_smoke"),
        "benchmark": release_payload.get("benchmark"),
        "rollback_docs": rollback_docs,
        "bundle_layout": {
            "training_root": "training",
            "benchmark_root": "benchmark",
            "runtime_root": "runtime",
            "rollback_docs_root": "docs/rollback",
            "readme": _bundle_rel(readme_path, bundle_root),
        },
        "source_artifacts": copied_sources,
        "bundle_files": _collect_bundle_files(bundle_root),
    }
    _write_json(bundle_root / "bundle_manifest.json", bundle_manifest)

    print(
        "Wrote reviewable candidate bundle: "
        f"{bundle_root} (decision={release_payload.get('decision')})"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
