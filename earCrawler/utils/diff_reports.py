from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path
from typing import Any, Dict


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def diff_text(left: Path, right: Path) -> Dict[str, Any]:
    a = _read_lines(left)
    b = _read_lines(right)
    diff = list(
        difflib.unified_diff(a, b, fromfile=str(left), tofile=str(right), lineterm="")
    )
    changed = any(line.startswith(('+', '-')) for line in diff[2:])
    return {"changed": changed, "diff": "\n".join(diff)}


def _normalize_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _normalize_json(obj[k]) for k in sorted(obj)}
    if isinstance(obj, list):
        return sorted((_normalize_json(x) for x in obj), key=lambda x: json.dumps(x, sort_keys=True))
    return obj


def diff_srj(left: Path, right: Path) -> Dict[str, Any]:
    a = _normalize_json(json.loads(left.read_text(encoding="utf-8")))
    b = _normalize_json(json.loads(right.read_text(encoding="utf-8")))
    a_str = json.dumps(a, sort_keys=True, indent=2)
    b_str = json.dumps(b, sort_keys=True, indent=2)
    diff = list(
        difflib.unified_diff(
            a_str.splitlines(), b_str.splitlines(), fromfile=str(left), tofile=str(right), lineterm=""
        )
    )
    changed = any(line.startswith(('+', '-')) for line in diff[2:])
    return {"changed": changed, "diff": "\n".join(diff)}


def write_report(result: Dict[str, Any], txt_path: Path | None, json_path: Path | None) -> None:
    if txt_path:
        txt_path.write_text(result.get("diff", ""), encoding="utf-8")
    if json_path:
        json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diff utility")
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--txt")
    parser.add_argument("--json")
    parser.add_argument("--srj", action="store_true")
    args = parser.parse_args()

    left = Path(args.left)
    right = Path(args.right)
    if args.srj or left.suffix == ".srj" or right.suffix == ".srj":
        result = diff_srj(left, right)
    else:
        result = diff_text(left, right)

    txt_path = Path(args.txt) if args.txt else None
    json_path = Path(args.json) if args.json else None
    write_report(result, txt_path, json_path)
    print(json.dumps(result))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
