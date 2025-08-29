from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

# Globs representing inputs that influence the KG build.
INCLUDE_GLOBS = [
    "kg/**/*.ttl",
    "kg/source/**/*",
    "tests/fixtures/cassettes/**/*",
    "api_clients/**/*",
    "earCrawler/kg/**/*.py",
    "tools/versions.json",
    "kg/queries/**/*.rq",
    "kg/assembler/**/*",
    "kg/scripts/**/*",
]

EXCLUDE_GLOBS = [
    "kg/prov/**",
    "kg/.kgstate/**",
    "kg/snapshots/**",
    "kg/reports/**",
]


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_files(root: Path) -> Iterable[Path]:
    seen = set()
    for pattern in INCLUDE_GLOBS:
        for p in root.glob(pattern):
            if p.is_file():
                skip = False
                for ex in EXCLUDE_GLOBS:
                    if p.match(ex):
                        skip = True
                        break
                if not skip:
                    rp = p.relative_to(root)
                    if rp not in seen:
                        seen.add(rp)
                        yield p


def build_manifest(root: Path) -> Dict[str, str]:
    files = {}
    for p in _iter_files(root):
        files[p.as_posix().replace("\\", "/")] = _hash_file(p)
    digest = hashlib.sha256(
        "".join(f"{k}:{files[k]}" for k in sorted(files)).encode("utf-8")
    ).hexdigest()
    return {"files": files, "digest": digest}


def load_manifest(path: Path) -> Dict[str, str] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def diff_manifests(old: Dict[str, str] | None, new: Dict[str, str]) -> List[str]:
    if not old:
        return sorted(new["files"].keys())
    changed: List[str] = []
    all_paths = set(old.get("files", {}).keys()) | set(new["files"].keys())
    for p in sorted(all_paths):
        if old.get("files", {}).get(p) != new["files"].get(p):
            changed.append(p)
    return changed


def write_manifest(manifest: Dict[str, str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="KG incremental state helper")
    parser.add_argument("--manifest", default="kg/.kgstate/manifest.json")
    parser.add_argument("--status", default="kg/reports/incremental-status.json")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest_path = (root / args.manifest).resolve()
    status_path = (root / args.status).resolve()

    new_manifest = build_manifest(root)
    old_manifest = load_manifest(manifest_path)
    changed_paths = diff_manifests(old_manifest, new_manifest)
    changed = bool(changed_paths)

    status = {"changed": changed, "paths": changed_paths, "count": len(changed_paths)}
    status_path.parent.mkdir(parents=True, exist_ok=True)
    with status_path.open("w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, sort_keys=True)

    if changed or not manifest_path.exists():
        write_manifest(new_manifest, manifest_path)

    print(json.dumps(status))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
