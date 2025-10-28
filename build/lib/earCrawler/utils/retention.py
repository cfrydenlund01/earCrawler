from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Tuple

MB = 1024 * 1024


@dataclass
class RetentionPolicy:
    max_days: int | None = None
    max_total_mb: int | None = None
    max_file_mb: int | None = None
    keep_last_n: int = 0

    def override(
        self,
        max_days: int | None = None,
        max_total_mb: int | None = None,
        max_file_mb: int | None = None,
        keep_last_n: int | None = None,
    ) -> "RetentionPolicy":
        pol = RetentionPolicy(**asdict(self))
        if max_days is not None:
            pol.max_days = max_days
        if max_total_mb is not None:
            pol.max_total_mb = max_total_mb
        if max_file_mb is not None:
            pol.max_file_mb = max_file_mb
        if keep_last_n is not None:
            pol.keep_last_n = keep_last_n
        return pol


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _whitelist() -> List[Path]:
    roots: List[Path] = [
        Path("kg").resolve(),
        Path(".cache/api").resolve(),
    ]
    app = os.getenv("APPDATA") or str(Path.home())
    roots.append((Path(app) / "EarCrawler" / "spool").resolve())
    prog = os.getenv("PROGRAMDATA") or app
    roots.append((Path(prog) / "EarCrawler" / "spool").resolve())
    return roots


def _is_whitelisted(p: Path) -> bool:
    rp = p.resolve()
    for root in _whitelist():
        try:
            rp.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _iter_files(base: Path) -> Iterable[Path]:
    for p in base.rglob("*"):
        if p.is_file():
            yield p


def _evaluate(base: Path, policy: RetentionPolicy) -> Tuple[List[dict], int]:
    files = sorted(
        _iter_files(base),
        key=lambda p: (p.stat().st_mtime, p.as_posix()),
        reverse=True,
    )
  
    protected = set(files[: policy.keep_last_n]) if policy.keep_last_n > 0 else set()
    now = _now().timestamp()
    candidates: List[dict] = []
    remaining: List[Path] = []
    for p in files:
        if p in protected:
            remaining.append(p)
            continue
        size = p.stat().st_size
        age_days = (now - p.stat().st_mtime) / 86400
        reason = None
        if policy.max_days is not None and age_days > policy.max_days:
            reason = "age"
        elif policy.max_file_mb is not None and size > policy.max_file_mb * MB:
            reason = "size"
        if reason:
            candidates.append({"path": str(p), "size": size, "reason": reason})
        else:
            remaining.append(p)
    if policy.max_total_mb is not None:
        total = sum(p.stat().st_size for p in remaining)
        limit = policy.max_total_mb * MB
        if total > limit:
            for p in sorted(remaining, key=lambda p: p.stat().st_mtime):
                if total <= limit:
                    break
                size = p.stat().st_size
                candidates.append({"path": str(p), "size": size, "reason": "excess"})
                total -= size
    candidates.sort(key=lambda c: c["path"])
    return candidates, len(files)


def _delete(paths: Iterable[dict]) -> List[dict]:
    deleted: List[dict] = []
    for info in paths:
        p = Path(info["path"])
        if p.exists():
            try:
                p.unlink()
            except PermissionError:
                shutil.rmtree(p, ignore_errors=True)
        deleted.append(info)
    return deleted


def gc_paths(
    paths: Iterable[Path],
    policy: RetentionPolicy,
    dry_run: bool = True,
    audit: bool = True,
) -> dict:
    candidates: List[dict] = []
    errors: List[str] = []
    for base in paths:
        if not base.exists():
            continue
        if not _is_whitelisted(base):
            errors.append(f"{base} outside whitelist")
            continue
        cands, _ = _evaluate(base, policy)
        candidates.extend(cands)
    deleted: List[dict] = []
    if not dry_run and candidates:
        deleted = _delete(candidates)
        if audit and deleted:
            ts = _iso(_now())
            report_dir = Path("kg/reports")
            report_dir.mkdir(parents=True, exist_ok=True)
            safe_ts = ts.replace(":", "-")
            audit_path = report_dir / f"gc-audit-{safe_ts}.json"
            with audit_path.open("w", encoding="utf-8") as fh:
                json.dump({"timestamp": ts, "deleted": deleted}, fh, indent=2)
    return {"candidates": candidates, "errors": errors, "deleted": deleted}


DEFAULT_POLICIES = {
    "telemetry": RetentionPolicy(max_days=30, max_total_mb=256, max_file_mb=8, keep_last_n=10),
    "cache": RetentionPolicy(max_days=30, max_total_mb=512, max_file_mb=64, keep_last_n=10),
    "kg": RetentionPolicy(max_days=30, max_total_mb=1024, max_file_mb=256, keep_last_n=10),
    "audit": RetentionPolicy(max_days=30, max_total_mb=256, max_file_mb=8, keep_last_n=10),
    "bundle": RetentionPolicy(max_days=90, max_total_mb=4096, max_file_mb=512, keep_last_n=3),
}


def run_gc(
    target: str = "all",
    dry_run: bool = True,
    max_days: int | None = None,
    max_total_mb: int | None = None,
    max_file_mb: int | None = None,
    keep_last_n: int | None = None,
) -> dict:
    targets = ["telemetry", "cache", "kg", "audit", "bundle"] if target == "all" else [target]
    all_candidates: List[dict] = []
    errors: List[str] = []
    policies: dict[str, dict] = {}
    deleted: List[dict] = []

    paths_map = {
        "telemetry": [
            Path(os.getenv("APPDATA") or str(Path.home())) / "EarCrawler" / "spool",
            Path(os.getenv("PROGRAMDATA") or (os.getenv("APPDATA") or str(Path.home())))
            / "EarCrawler"
            / "spool",
        ],
        "cache": [
            Path(".cache/api/tradegov"),
            Path(".cache/api/federalregister"),
        ],
        "kg": [
            Path("kg/reports"),
            Path("kg/snapshots"),
            Path("kg/.kgstate"),
            Path("kg/target/tdb2"),
            Path("kg/prov"),
        ],
        "audit": [
            Path(os.getenv("APPDATA") or str(Path.home())) / "EarCrawler" / "audit",
            Path(os.getenv("PROGRAMDATA") or (os.getenv("APPDATA") or str(Path.home()))) / "EarCrawler" / "audit",
        ],
        "bundle": [
            Path("dist/offline_bundle"),
        ],
    }

    for tgt in targets:
        policy = DEFAULT_POLICIES[tgt].override(max_days, max_total_mb, max_file_mb, keep_last_n)
        policies[tgt] = asdict(policy)
        report = gc_paths(paths_map[tgt], policy, dry_run=dry_run, audit=not dry_run)
        for c in report["candidates"]:
            c["target"] = tgt
        all_candidates.extend(report["candidates"])
        errors.extend(report["errors"])
        deleted.extend(report["deleted"])

    return {
        "dry_run": dry_run,
        "targets": targets,
        "policies": policies,
        "candidates": sorted(all_candidates, key=lambda c: c["path"]),
        "errors": errors,
        "deleted": deleted,
    }
