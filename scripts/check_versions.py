from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
VERSIONS_FILE = ROOT / "tools" / "versions.json"

def load_versions() -> dict[str, str]:
    try:
        return json.loads(VERSIONS_FILE.read_text())
    except Exception:
        return {}


def check_component(name: str, pattern: str, expected: str) -> list[str]:
    cmd = [
        "rg",
        "-n",
        pattern,
        str(ROOT),
        "-g",
        "!tools/versions.json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    mismatches: list[str] = []
    regex = re.compile(pattern)
    for line in proc.stdout.splitlines():
        m = regex.search(line)
        if not m:
            continue
        found = m.group(1)
        if found != expected:
            mismatches.append(line)
    return mismatches


def main() -> int:
    versions = load_versions()
    jena = versions.get("jena", "")
    fuseki = versions.get("fuseki", "")
    print(f"Jena version: {jena}")
    if fuseki:
        print(f"Fuseki version: {fuseki}")
    errors: list[str] = []
    if jena:
        errors += check_component("jena", r"apache-jena-(\d+\.\d+\.\d+)", jena)
    if fuseki:
        errors += check_component(
            "fuseki", r"apache-jena-fuseki-(\d+\.\d+\.\d+)", fuseki
        )
    if errors:
        print("Found mismatched versions:")
        for line in errors:
            print(line)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
