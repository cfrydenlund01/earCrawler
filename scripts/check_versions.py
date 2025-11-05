from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
VERSIONS_FILE = ROOT / "tools" / "versions.json"

def load_versions() -> dict[str, Any]:
    try:
        return json.loads(VERSIONS_FILE.read_text())
    except Exception:
        return {}


def check_component(name: str, pattern: str, expected: str) -> list[str]:
    mismatches: list[str] = []
    regex = re.compile(pattern)
    try:
        tracked = subprocess.run(
            ["git", "ls-files"],
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        ).stdout.splitlines()
    except subprocess.CalledProcessError:
        tracked = []
    for rel_path in tracked:
        if rel_path == "tools/versions.json":
            continue
        path = ROOT / rel_path
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = regex.search(line)
            if not match:
                continue
            found = match.group(1)
            if found != expected:
                mismatches.append(f"{rel_path}:{lineno}:{line.strip()}")
    return mismatches


def _extract_version(value) -> str:
    if isinstance(value, dict):
        return str(value.get("version", ""))
    if isinstance(value, str):
        return value
    return ""


def main() -> int:
    versions = load_versions()
    jena_version = _extract_version(versions.get("jena"))
    fuseki_version = _extract_version(versions.get("fuseki"))
    if jena_version:
        print(f"Jena version: {jena_version}")
    else:
        print("Jena version: <missing>")
    if fuseki_version:
        print(f"Fuseki version: {fuseki_version}")
    errors: list[str] = []
    if jena_version:
        errors += check_component("jena", r"apache-jena-(\d+\.\d+\.\d+)", jena_version)
    if fuseki_version:
        errors += check_component(
            "fuseki", r"apache-jena-fuseki-(\d+\.\d+\.\d+)", fuseki_version
        )
    if errors:
        print("Found mismatched versions:")
        for line in errors:
            print(line)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
