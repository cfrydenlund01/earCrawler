from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class CmdResult:
    argv: list[str]
    exit_code: int
    log_path: Path
    started_at_utc: str
    finished_at_utc: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return "unknown"
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("._-")
    return value or "unknown"


def _unique_dir(base: Path, name: str) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    root = base / name
    if not root.exists():
        root.mkdir(parents=True, exist_ok=False)
        return root
    for idx in range(1, 1000):
        candidate = base / f"{name}_{idx:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
    raise RuntimeError(f"Unable to create unique directory under {base} for {name}")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _run_cmd(*, argv: list[str], log_path: Path, cwd: Path | None = None) -> CmdResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = _utc_now_iso()
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd or Path.cwd()),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"started_at_utc={started}\n")
        log.write("command=" + " ".join(argv) + "\n\n")
        for line in proc.stdout:
            log.write(line)
    exit_code = proc.wait()
    finished = _utc_now_iso()
    with log_path.open("a", encoding="utf-8") as log:
        log.write("\n")
        log.write(f"finished_at_utc={finished}\n")
        log.write(f"exit_code={exit_code}\n")
    return CmdResult(
        argv=argv,
        exit_code=int(exit_code),
        log_path=log_path,
        started_at_utc=started,
        finished_at_utc=finished,
    )


def _try_run_capture(argv: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return int(proc.returncode), (proc.stdout or "").strip()
    except Exception as exc:
        return 1, str(exc)


def _git_provenance() -> dict[str, Any]:
    code, head = _try_run_capture(["git", "rev-parse", "HEAD"])
    head = head if code == 0 else ""
    code2, status = _try_run_capture(["git", "status", "--porcelain"])
    status_lines = [line for line in status.splitlines() if line.strip()] if code2 == 0 else []
    return {
        "git_head": head,
        "git_dirty": bool(status_lines),
        "git_status_porcelain": status_lines,
    }


def _compact_index_meta(index_meta_path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "meta_path": str(index_meta_path),
        "exists": index_meta_path.exists(),
    }
    if not index_meta_path.exists():
        return payload
    stat = index_meta_path.stat()
    payload["file_size_bytes"] = stat.st_size
    payload["mtime_utc"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    try:
        full = _read_json(index_meta_path)
        payload.update(
            {
                "schema_version": full.get("schema_version"),
                "build_timestamp_utc": full.get("build_timestamp_utc"),
                "corpus_digest": full.get("corpus_digest"),
                "corpus_schema_version": full.get("corpus_schema_version"),
                "doc_count": full.get("doc_count"),
                "embedding_model": full.get("embedding_model"),
                "snapshot": full.get("snapshot") if isinstance(full.get("snapshot"), dict) else None,
            }
        )
    except Exception as exc:
        payload["error"] = str(exc)
    return payload


def _iter_snapshot_records(snapshot_path: Path) -> Iterable[dict[str, Any]]:
    with snapshot_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            yield json.loads(stripped)


def _sort_key_section(section: str) -> tuple[int, int, str]:
    # section is expected to be like "740.10" (no EAR- prefix)
    match = re.match(r"^(?P<major>\\d+)\\.(?P<minor>\\d+)(?P<suffix>.*)$", section.strip())
    if not match:
        return (10**9, 10**9, section)
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    suffix = match.group("suffix") or ""
    return (major, minor, suffix)


def _infer_heading(record: dict[str, Any]) -> str:
    heading = str(record.get("heading") or "").strip()
    if heading:
        return heading
    text = str(record.get("text") or "")
    for line in text.splitlines():
        cand = line.strip()
        if not cand:
            continue
        # Prefer a line that looks like "§ 740.10 ..." when present.
        if cand.startswith("§ "):
            cand = cand.replace("§", "").strip()
            cand = re.sub(r"^\\d+(?:\\.\\d+)*\\s+", "", cand).strip()
            return cand or "Untitled"
        if "§" in cand:
            cand = cand.replace("§", "").strip()
            cand = re.sub(r"^\\d+(?:\\.\\d+)*\\s+", "", cand).strip()
            return cand or "Untitled"
    return "Untitled"


def generate_snapshot_universe_dataset(
    *,
    snapshot_path: Path,
    out_dir: Path,
    dataset_id: str = "snapshot_universe.v2",
    parts_allowlist: set[str] | None = None,
) -> tuple[Path, Path, int]:
    """
    Generates a tiny `fr_coverage_universe` dataset (one item per top-level section).

    Output files (written under out_dir):
      - snapshot_universe.v2.jsonl
      - manifest.snapshot_universe.json
    """
    from earCrawler.rag import pipeline

    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_file = out_dir / "snapshot_universe.v2.jsonl"
    manifest_file = out_dir / "manifest.snapshot_universe.json"

    items_by_section: dict[str, dict[str, Any]] = {}
    for rec in _iter_snapshot_records(snapshot_path):
        norm = pipeline._normalize_section_id(rec.get("section_id"))
        if not norm or not norm.startswith("EAR-"):
            continue
        # Only top-level CFR sections (exclude subsections/paragraph identifiers).
        if "(" in norm or "#" in norm:
            continue
        section = norm.removeprefix("EAR-").strip()
        if not section:
            continue
        part = section.split(".", 1)[0]
        if parts_allowlist is not None and part not in parts_allowlist:
            continue
        heading = _infer_heading(rec)
        heading = heading.rstrip(".").strip()
        heading = re.sub(rf"^(?:§\\s*)?{re.escape(section)}\\s*", "", heading).strip()
        heading = heading or "Untitled"
        question = f"15 CFR {section} § {section} {heading}."
        ear_id = f"EAR-{section}"
        items_by_section[section] = {
            "id": f"snap:{section}",
            "task": "fr_coverage_universe",
            "question": question,
            "ground_truth": {
                "answer_text": "Snapshot-universe coverage item.",
                "label": "unanswerable",
            },
            "ear_sections": [ear_id],
            "kg_entities": [],
            "evidence": {"doc_spans": [], "kg_nodes": [], "kg_paths": []},
        }

    items = [items_by_section[k] for k in sorted(items_by_section.keys(), key=_sort_key_section)]
    with dataset_file.open("w", encoding="utf-8", newline="\n") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    manifest = {
        "datasets": [
            {
                "num_items": len(items),
                "file": dataset_file.name,
                "task": "fr_coverage_universe",
                "description": (
                    "Snapshot-derived expected universe for CFR Title 15 parts "
                    + ("/".join(sorted(parts_allowlist)) if parts_allowlist else "<all parts>")
                    + " (generated from offline snapshot payload)."
                ),
                "version": 2,
                "id": dataset_id,
            }
        ]
    }
    _write_json(manifest_file, manifest)
    return manifest_file, dataset_file, len(items)


def _format_bool_pass(exit_code: int) -> str:
    return "PASS" if exit_code == 0 else "FAIL"


def _maybe_load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return _read_json(path)
    except Exception:
        return None


def write_readme(
    *,
    out_dir: Path,
    scorecard: dict[str, Any],
    fr_summary: dict[str, Any] | None,
    eval_json: dict[str, Any] | None,
) -> None:
    lines: list[str] = []
    lines.append("# Results bundle")
    lines.append("")
    lines.append(f"- Created (UTC): `{scorecard['bundle']['created_at_utc']}`")
    lines.append(f"- Snapshot: `{scorecard['provenance']['snapshot'].get('snapshot_id') or 'unknown'}`")
    lines.append(f"- Git HEAD: `{scorecard['provenance']['git'].get('git_head') or 'unknown'}`")
    lines.append("")
    lines.append("## Gates")
    checks = scorecard.get("checks") or {}
    lines.append(f"- Unit tests (`pytest -q`): **{_format_bool_pass(checks['pytest']['exit_code'])}**")
    lines.append(f"- FR coverage (v2 universe): **{_format_bool_pass(checks['fr_coverage']['exit_code'])}**")
    lines.append(f"- Golden gate (phase2): **{_format_bool_pass(checks['golden_gate']['exit_code'])}**")
    eval_exit = int((checks.get('small_eval') or {}).get("exit_code") or 0)
    lines.append(f"- Small eval (citation/trace packs): **{_format_bool_pass(eval_exit)}**")
    lines.append("")
    lines.append("## Key metrics")
    if fr_summary and isinstance(fr_summary.get("summary"), dict):
        s = fr_summary["summary"]
        miss_rate = s.get("missing_in_retrieval_rate")
        worst_rate = s.get("worst_missing_in_retrieval_rate")
        miss_r = s.get("num_missing_in_retrieval")
        miss_c = s.get("num_missing_in_corpus")
        if isinstance(miss_rate, (int, float)) and isinstance(worst_rate, (int, float)):
            lines.append(
                f"- Coverage missing rate: `{miss_rate:.4f}` (worst `{worst_rate:.4f}`), "
                f"missing_in_retrieval=`{miss_r}`, missing_in_corpus=`{miss_c}`"
            )
        else:
            lines.append("- Coverage missing rate: `n/a` (missing rates not present in fr_coverage_summary.json)")
    else:
        lines.append("- Coverage missing rate: `n/a` (fr_coverage_summary.json missing or unreadable)")

    if eval_json:
        grounded_rate = eval_json.get("grounded_rate")
        pr = ((eval_json.get("citation_pr") or {}).get("micro") or {})
        prec = pr.get("precision")
        rec = pr.get("recall")
        lines.append(f"- Grounded rate: `{grounded_rate:.4f}`" if isinstance(grounded_rate, (int, float)) else "- Grounded rate: `n/a`")
        if isinstance(prec, (int, float)) and isinstance(rec, (int, float)):
            lines.append(f"- Citation micro P/R: `{prec:.4f}` / `{rec:.4f}`")
        else:
            lines.append("- Citation micro P/R: `n/a`")
    else:
        lines.append("- Grounded rate: `n/a` (small_eval.json missing or unreadable)")
        lines.append("- Citation micro P/R: `n/a` (small_eval.json missing or unreadable)")

    lines.append("")
    lines.append("## Artifacts")
    lines.append("- `bundle_scorecard.json` (diff-friendly summary)")
    lines.append("- `fr_coverage_report.json`, `fr_coverage_summary.json`, `phase1_blocker.md`")
    lines.append("- `small_eval.json`, `small_eval.md`, `<run_id>/trace_packs/`")
    lines.append("- `pytest_unit.log`, `fr_coverage.log`, `golden_gate.log`, `small_eval.log`")
    lines.append("")
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Produce a dated results bundle under dist/results/.")
    parser.add_argument("--snapshot-id", default=None, help="Snapshot id (defaults from manifest/index meta if available).")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="Offline snapshot payload JSONL (defaults to snapshots/offline/<snapshot_id>/snapshot.jsonl when possible).",
    )
    parser.add_argument(
        "--snapshot-manifest",
        type=Path,
        default=None,
        help="Offline snapshot manifest JSON (defaults to snapshots/offline/<snapshot_id>/manifest.json when possible).",
    )
    parser.add_argument(
        "--index-meta",
        type=Path,
        default=Path("data") / "faiss" / "index.meta.json",
        help="FAISS index meta JSON (used only for provenance).",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("data") / "faiss" / "retrieval_corpus.jsonl",
        help="Corpus JSONL to validate references against for FR coverage.",
    )
    parser.add_argument("--retrieval-k", type=int, default=10, help="Top-k for FR coverage rank checks.")
    parser.add_argument("--max-missing-rate", type=float, default=0.10, help="Fail FR coverage if worst missing rate exceeds this.")
    parser.add_argument(
        "--coverage-manifest",
        type=Path,
        default=None,
        help="Optional: pre-built FR coverage manifest JSON (otherwise generated from --snapshot when available).",
    )
    parser.add_argument(
        "--eval-dataset-id",
        default="golden_phase2.v1",
        help="Dataset id label for the small eval run (used by offline golden mode).",
    )
    parser.add_argument("--eval-max-items", type=int, default=5, help="Max items for the small eval run.")
    parser.add_argument(
        "--eval-mode",
        choices=["golden_offline", "remote_llm"],
        default="golden_offline",
        help="Which small eval to run: deterministic offline golden fixtures or remote LLM eval harness.",
    )
    parser.add_argument(
        "--out-base",
        type=Path,
        default=Path("dist") / "results",
        help="Base output directory for results bundles.",
    )
    parser.add_argument(
        "--require-eval",
        action="store_true",
        help="Fail the bundle command if the small eval run fails.",
    )
    args = parser.parse_args(argv)

    created_at = _utc_now_iso()
    git_info = _git_provenance()

    index_meta_compact = _compact_index_meta(args.index_meta)

    snapshot_id = _safe_name(args.snapshot_id or "")
    if snapshot_id == "unknown":
        snap = index_meta_compact.get("snapshot") if isinstance(index_meta_compact.get("snapshot"), dict) else None
        inferred = str((snap or {}).get("snapshot_id") or "").strip()
        if inferred:
            snapshot_id = _safe_name(inferred)
    snapshot_manifest_path: Path | None = args.snapshot_manifest
    snapshot_path: Path | None = args.snapshot

    if snapshot_manifest_path is None and snapshot_id != "unknown":
        candidate = Path("snapshots") / "offline" / snapshot_id / "manifest.json"
        snapshot_manifest_path = candidate if candidate.exists() else None
    if snapshot_path is None and snapshot_id != "unknown":
        candidate = Path("snapshots") / "offline" / snapshot_id / "snapshot.jsonl"
        snapshot_path = candidate if candidate.exists() else None

    snapshot_manifest: dict[str, Any] | None = None
    if snapshot_manifest_path and snapshot_manifest_path.exists():
        snapshot_manifest = _read_json(snapshot_manifest_path)
        manifest_snapshot_id = str(snapshot_manifest.get("snapshot_id") or "").strip()
        if manifest_snapshot_id:
            snapshot_id = _safe_name(manifest_snapshot_id)

    out_dir = _unique_dir(
        args.out_base,
        f"{datetime.now(timezone.utc).strftime('%Y%m%d')}_{snapshot_id}",
    )
    (out_dir / "command_history.txt").write_text("", encoding="utf-8")

    def record(line: str) -> None:
        with (out_dir / "command_history.txt").open("a", encoding="utf-8") as handle:
            handle.write(line.rstrip() + "\n")

    record(f"created_at_utc={created_at}")
    record(f"out_dir={out_dir}")
    record(f"python_exe={sys.executable}")
    record(f"snapshot_id={snapshot_id}")
    record(f"snapshot_path={snapshot_path or ''}")
    record(f"snapshot_manifest_path={snapshot_manifest_path or ''}")
    record(f"index_meta_path={args.index_meta}")
    record(f"corpus_path={args.corpus}")
    record(f"retrieval_k={args.retrieval_k}")
    record(f"max_missing_rate={args.max_missing_rate}")
    record(f"eval_dataset_id={args.eval_dataset_id}")
    record(f"eval_max_items={args.eval_max_items}")
    record(f"eval_mode={args.eval_mode}")
    record(f"git_head={git_info.get('git_head') or ''}")
    record(f"git_dirty={git_info.get('git_dirty')}")

    # Provenance files (small + diff-friendly).
    snapshot_prov: dict[str, Any] = {"snapshot_id": snapshot_id}
    if snapshot_manifest:
        snapshot_prov.update(
            {
                "manifest_path": str(snapshot_manifest_path),
                "manifest_version": snapshot_manifest.get("manifest_version"),
                "created_at": snapshot_manifest.get("created_at"),
                "scope": snapshot_manifest.get("scope"),
                "payload": snapshot_manifest.get("payload"),
                "source": snapshot_manifest.get("source"),
            }
        )
    if snapshot_path and snapshot_path.exists():
        stat = snapshot_path.stat()
        snapshot_prov["snapshot_path"] = str(snapshot_path)
        snapshot_prov["snapshot_size_bytes"] = stat.st_size
        snapshot_prov["snapshot_mtime_utc"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

    _write_json(out_dir / "provenance.snapshot.json", snapshot_prov)
    _write_json(out_dir / "provenance.index.json", index_meta_compact)
    _write_json(out_dir / "provenance.git.json", git_info)

    # 0) Snapshot validation + universe dataset generation (if snapshot available).
    snapshot_validation = None
    parts_allowlist: set[str] | None = None
    if snapshot_manifest and isinstance(snapshot_manifest.get("scope"), dict):
        parts = snapshot_manifest["scope"].get("parts")
        if isinstance(parts, list) and parts:
            parts_allowlist = {str(p) for p in parts if str(p).strip()}
    if snapshot_path and snapshot_path.exists():
        snap_argv = [sys.executable, "-m", "earCrawler.cli", "rag-index", "validate-snapshot", "--snapshot", str(snapshot_path)]
        if snapshot_manifest_path and snapshot_manifest_path.exists():
            snap_argv.extend(["--snapshot-manifest", str(snapshot_manifest_path)])
        snapshot_validation = _run_cmd(argv=snap_argv, log_path=out_dir / "snapshot_validation.log")
        record(f"exit.snapshot_validate={snapshot_validation.exit_code}")
    else:
        record("skip.snapshot_validate=missing_snapshot_path")

    coverage_manifest_path = args.coverage_manifest or (out_dir / "manifest.snapshot_universe.json")
    if args.coverage_manifest is None and snapshot_path and snapshot_path.exists():
        try:
            manifest_path, dataset_path, num_items = generate_snapshot_universe_dataset(
                snapshot_path=snapshot_path,
                out_dir=out_dir,
                parts_allowlist=parts_allowlist,
            )
            record(f"snapshot_universe_manifest={manifest_path}")
            record(f"snapshot_universe_dataset={dataset_path} items={num_items}")
            coverage_manifest_path = manifest_path
        except Exception as exc:
            record(f"error.snapshot_universe={exc}")

    # 1) Unit tests.
    pytest_unit = _run_cmd(
        argv=[sys.executable, "-m", "pytest", "-q"],
        log_path=out_dir / "pytest_unit.log",
    )
    record(f"exit.pytest_unit={pytest_unit.exit_code}")

    # 2) FR coverage (v2 universe).
    fr_report = out_dir / "fr_coverage_report.json"
    fr_summary = out_dir / "fr_coverage_summary.json"
    blocker_note = out_dir / "phase1_blocker.md"
    fr_cov = _run_cmd(
        argv=[
            sys.executable,
            "-m",
            "earCrawler.cli",
            "eval",
            "fr-coverage",
            "--manifest",
            str(coverage_manifest_path),
            "--corpus",
            str(args.corpus),
            "--dataset-id",
            "snapshot_universe.v2",
            "--retrieval-k",
            str(args.retrieval_k),
            "--max-missing-rate",
            str(args.max_missing_rate),
            "--out",
            str(fr_report),
            "--summary-out",
            str(fr_summary),
            "--write-blocker-note",
            str(blocker_note),
        ],
        log_path=out_dir / "fr_coverage.log",
    )
    record(f"exit.fr_coverage={fr_cov.exit_code}")

    # 3) Golden gate.
    golden_gate = _run_cmd(
        argv=[sys.executable, "-m", "pytest", "-q", "tests/golden/test_phase2_golden_gate.py"],
        log_path=out_dir / "golden_gate.log",
    )
    record(f"exit.golden_gate={golden_gate.exit_code}")

    # 4) Small eval (produces citation metrics + trace packs).
    small_eval_json_path = out_dir / "small_eval.json"
    small_eval_md_path = out_dir / "small_eval.md"
    if args.eval_mode == "remote_llm":
        small_eval_argv = [
            sys.executable,
            "-m",
            "scripts.eval.eval_rag_llm",
            "--dataset-id",
            str(args.eval_dataset_id),
            "--manifest",
            str(Path("eval") / "manifest.json"),
            "--max-items",
            str(args.eval_max_items),
            "--out-json",
            str(small_eval_json_path),
            "--out-md",
            str(small_eval_md_path),
        ]
    else:
        small_eval_argv = [
            sys.executable,
            "-m",
            "scripts.eval.eval_golden_phase2_offline",
            "--dataset-id",
            str(args.eval_dataset_id),
            "--max-items",
            str(args.eval_max_items),
            "--out-json",
            str(small_eval_json_path),
            "--out-md",
            str(small_eval_md_path),
        ]
    small_eval = _run_cmd(argv=small_eval_argv, log_path=out_dir / "small_eval.log")
    record(f"exit.small_eval={small_eval.exit_code}")

    fr_summary_obj = _maybe_load(fr_summary)
    eval_obj = _maybe_load(small_eval_json_path)

    scorecard = {
        "bundle": {
            "created_at_utc": created_at,
            "out_dir": str(out_dir),
        },
        "provenance": {
            "git": git_info,
            "snapshot": snapshot_prov,
            "index": index_meta_compact,
        },
        "checks": {
            "snapshot_validate": {"exit_code": int(snapshot_validation.exit_code) if snapshot_validation else None},
            "pytest": {"exit_code": int(pytest_unit.exit_code)},
            "fr_coverage": {
                "exit_code": int(fr_cov.exit_code),
                "max_missing_rate": float(args.max_missing_rate),
                "summary_path": str(fr_summary),
            },
            "golden_gate": {"exit_code": int(golden_gate.exit_code)},
            "small_eval": {
                "exit_code": int(small_eval.exit_code),
                "dataset_id": str(args.eval_dataset_id),
                "eval_json_path": str(small_eval_json_path),
            },
        },
    }

    # Add key numbers (if available) for diffability.
    if fr_summary_obj and isinstance(fr_summary_obj.get("summary"), dict):
        s = fr_summary_obj["summary"]
        scorecard["checks"]["fr_coverage"]["missing_in_retrieval_rate"] = s.get("missing_in_retrieval_rate")
        scorecard["checks"]["fr_coverage"]["worst_missing_in_retrieval_rate"] = s.get("worst_missing_in_retrieval_rate")
        scorecard["checks"]["fr_coverage"]["num_missing_in_retrieval"] = s.get("num_missing_in_retrieval")
        scorecard["checks"]["fr_coverage"]["num_missing_in_corpus"] = s.get("num_missing_in_corpus")
    if eval_obj:
        scorecard["checks"]["small_eval"]["grounded_rate"] = eval_obj.get("grounded_rate")
        micro = ((eval_obj.get("citation_pr") or {}).get("micro") or {})
        scorecard["checks"]["small_eval"]["citation_micro_precision"] = micro.get("precision")
        scorecard["checks"]["small_eval"]["citation_micro_recall"] = micro.get("recall")

    _write_json(out_dir / "bundle_scorecard.json", scorecard)
    write_readme(out_dir=out_dir, scorecard=scorecard, fr_summary=fr_summary_obj, eval_json=eval_obj)

    required_exit_codes = [
        int(pytest_unit.exit_code),
        int(fr_cov.exit_code),
        int(golden_gate.exit_code),
    ]
    if snapshot_validation is not None:
        required_exit_codes.append(int(snapshot_validation.exit_code))
    if args.require_eval:
        required_exit_codes.append(int(small_eval.exit_code))

    overall_ok = all(code == 0 for code in required_exit_codes)
    return 0 if overall_ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
