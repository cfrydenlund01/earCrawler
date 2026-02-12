from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from earCrawler.kg.fuseki import running_fuseki
from earCrawler.config.llm_secrets import get_llm_config
from scripts.eval import eval_rag_llm


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _java_major_version(java_exe: Path) -> int | None:
    try:
        proc = subprocess.run(
            [str(java_exe), "-version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    output = (proc.stderr or "") + "\n" + (proc.stdout or "")
    # Examples:
    # - java version "1.8.0_202"  -> major 8
    # - openjdk version "17.0.8" -> major 17
    match = re.search(r'version\\s+\"(?P<major>\\d+)(?:\\.(?P<minor>\\d+))?', output)
    if not match:
        return None
    major = int(match.group("major"))
    if major == 1 and match.group("minor"):
        return int(match.group("minor"))
    return major


def _ensure_java_home() -> None:
    java_home = os.getenv("JAVA_HOME")
    if java_home:
        java_exe = Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")
        major = _java_major_version(java_exe)
        if major is not None and major >= 17:
            return
    candidates = sorted((Path("tools") / "jdk17").glob("jdk-*"))
    for cand in candidates:
        if (cand / "bin" / "java.exe").is_file() or (cand / "bin" / "java").is_file():
            os.environ["JAVA_HOME"] = str(cand.resolve())
            os.environ["PATH"] = str((cand / "bin").resolve()) + os.pathsep + os.environ.get("PATH", "")
            return
    raise RuntimeError(
        "JAVA_HOME not set and no local JDK found under tools/jdk17/. "
        "Install a JDK 17+ or set JAVA_HOME."
    )


def _safe_name(value: str) -> str:
    return value.replace("/", "-").replace(":", "-")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Production-like multihop KG expansion run (Fuseki-backed) with real LLM credentials."
    )
    parser.add_argument("--dataset-id", default="multihop_slice.v1")
    parser.add_argument("--manifest", type=Path, default=Path("eval") / "manifest.json")
    parser.add_argument("--max-items", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--db", type=Path, default=Path("fuseki_db"))
    parser.add_argument("--port", type=int, default=3030)
    parser.add_argument("--run-id", default=None, help="Defaults to multihop_kg_prodlike_<utcstamp>.")
    parser.add_argument("--out-dir", type=Path, default=Path("dist") / "ablations")
    parser.add_argument("--llm-provider", choices=["groq", "nvidia_nim"], default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument(
        "--failure-policy",
        choices=["disable", "error"],
        default="disable",
        help="KG expansion failure policy when Fuseki is unhealthy.",
    )
    parser.add_argument("--trace-pack-threshold", type=float, default=0.0)
    args = parser.parse_args(argv)

    _ensure_java_home()

    run_id = args.run_id or f"multihop_kg_prodlike_{_utc_stamp()}"
    out_dir = (Path(args.out_dir).resolve() / run_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    os.environ["EARCRAWLER_REMOTE_LLM_POLICY"] = "allow"
    os.environ["EARCRAWLER_ENABLE_REMOTE_LLM"] = "1"
    os.environ["EARCRAWLER_ENABLE_KG_EXPANSION"] = "1"
    os.environ["EARCRAWLER_KG_EXPANSION_MODE"] = "multihop_only"
    os.environ["EARCRAWLER_KG_EXPANSION_PROVIDER"] = "fuseki"
    os.environ["EARCRAWLER_KG_EXPANSION_FAILURE_POLICY"] = str(args.failure_policy)
    os.environ["EARCRAWLER_KG_EXPANSION_FUSEKI_HEALTHCHECK"] = "1"
    os.environ.setdefault("EARCRAWLER_KG_EXPANSION_FUSEKI_TIMEOUT", "5")
    os.environ.setdefault("EARCRAWLER_KG_EXPANSION_FUSEKI_RETRIES", "1")
    os.environ.setdefault("EARCRAWLER_KG_EXPANSION_FUSEKI_RETRY_BACKOFF_MS", "100")

    fuseki_url = f"http://localhost:{int(args.port)}/ear/sparql"
    os.environ["EARCRAWLER_FUSEKI_URL"] = fuseki_url

    cfg = get_llm_config(provider_override=args.llm_provider, model_override=args.llm_model)
    if not cfg.enable_remote:
        reason = cfg.remote_disabled_reason or "unknown"
        raise RuntimeError(f"Remote LLMs are disabled ({reason}).")
    if not (cfg.provider.api_key or "").strip():
        raise RuntimeError(
            "No LLM API key found for provider "
            f"{cfg.provider.provider!r}. Configure it in config/llm_secrets.env "
            "or via Windows Credential Manager."
        )
    provider = cfg.provider.provider
    model = cfg.provider.model or ""
    safe_model = _safe_name(model or "default")

    out_json = out_dir / f"{args.dataset_id}.kg_on.{provider}.{safe_model}.json"
    out_md = out_dir / f"{args.dataset_id}.kg_on.{provider}.{safe_model}.md"

    with running_fuseki(Path(args.db), dataset="/ear", port=int(args.port)):
        rc = eval_rag_llm.main(
            [
                "--dataset-id",
                str(args.dataset_id),
                "--manifest",
                str(args.manifest),
                "--llm-provider",
                provider,
                *(["--llm-model", str(args.llm_model)] if args.llm_model else []),
                "--top-k",
                str(int(args.top_k)),
                "--max-items",
                str(int(args.max_items)),
                "--kg-expansion",
                "1",
                "--multihop-only",
                "--trace-pack-threshold",
                str(float(args.trace_pack_threshold)),
                "--out-json",
                str(out_json),
                "--out-md",
                str(out_md),
            ]
        )

    if rc == 0:
        print(f"Wrote {out_json}")
        print(f"Wrote {out_md}")
        print(f"Trace packs under {out_dir / out_json.stem / 'trace_packs' / args.dataset_id}")
        print(f"Fuseki endpoint was {fuseki_url}")
        print(f"Run id label: {run_id}")
    return rc


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
