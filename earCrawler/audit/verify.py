from __future__ import annotations

import json
from pathlib import Path

from .ledger import verify_chain, verify_chain_report


def verify(path: Path) -> bool:
    return verify_chain(path)


def verify_report(path: Path) -> dict[str, object]:
    return verify_chain_report(path)


def verify_cli(path: Path) -> int:
    report = verify_report(path)
    ok = bool(report.get("ok"))
    print(json.dumps(report))
    return 0 if ok else 1
