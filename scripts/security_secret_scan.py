from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SecretPattern:
    name: str
    regex: re.Pattern[str]


PATTERNS: tuple[SecretPattern, ...] = (
    SecretPattern("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    SecretPattern("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    SecretPattern("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    SecretPattern("github_fine_grained_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{70,}\b")),
    SecretPattern("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
)


def _git_tracked_files(repo_root: Path) -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    files: list[Path] = []
    for line in proc.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        files.append(repo_root / rel)
    return files


def _iter_lines(path: Path) -> Iterable[tuple[int, str]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for idx, line in enumerate(handle, start=1):
                yield idx, line
    except UnicodeDecodeError:
        return


def _scan_file(path: Path, repo_root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    rel_path = path.relative_to(repo_root).as_posix()
    for line_number, line in _iter_lines(path):
        for pattern in PATTERNS:
            if pattern.regex.search(line):
                findings.append(
                    {
                        "path": rel_path,
                        "line": line_number,
                        "pattern": pattern.name,
                        "snippet": line.strip()[:200],
                    }
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan git-tracked text files for high-signal secret patterns."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root to scan (default: current directory).",
    )
    parser.add_argument(
        "--report-path",
        default="dist/security/secret_scan.json",
        help="Where to write the JSON report.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    report_path = Path(args.report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    findings: list[dict[str, object]] = []
    for file_path in _git_tracked_files(repo_root):
        if file_path.is_file():
            findings.extend(_scan_file(file_path, repo_root))

    payload = {
        "schema_version": "secret-scan.v1",
        "findings": findings,
        "finding_count": len(findings),
        "status": "passed" if not findings else "failed",
    }
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
