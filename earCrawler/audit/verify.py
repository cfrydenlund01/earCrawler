from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .ledger import verify_chain


def verify(path: Path) -> bool:
    return verify_chain(path)


def verify_cli(path: Path) -> int:
    ok = verify(path)
    report = {"path": str(path), "ok": ok}
    print(json.dumps(report))
    return 0 if ok else 1
