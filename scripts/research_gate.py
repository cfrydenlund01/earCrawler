import argparse
import subprocess
import sys
from pathlib import Path

research = Path.cwd() / "Research"
research.mkdir(exist_ok=True)


def run_pytest(pytest_args: list[str]) -> int:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *pytest_args], check=False
        )
        return result.returncode
    except FileNotFoundError:
        return 127


def verify_artifacts(paths: list[str]) -> list[str]:
    missing = []
    for p in paths:
        if not Path(p).exists():
            missing.append(p)
    return missing


def main():
    ap = argparse.ArgumentParser(
        description="Research gate: verify artifacts and run tests before advancing."
    )
    ap.add_argument("--name", required=True)
    ap.add_argument("--expect", action="append", default=[])
    ap.add_argument("--pytest", dest="pytest_args", nargs="*", default=[])
    ap.add_argument(
        "--log", action="store_true", help="Append to Research/decision_log.md"
    )
    ap.add_argument("--summary", default="")
    args = ap.parse_args()

    missing = verify_artifacts(args.expect)
    rc = run_pytest(args.pytest_args) if args.pytest_args else 0

    status = "pass"
    if missing or rc not in (0,):
        status = "fail"

    if args.log:
        # local import to avoid hard dependency
        import importlib.util, sys

        dl = Path("scripts/decision_log.py")
        if dl.exists():
            spec = importlib.util.spec_from_file_location("decision_log", str(dl))
            mod = importlib.util.module_from_spec(spec)  # type: ignore
            assert spec and spec.loader
            spec.loader.exec_module(mod)  # type: ignore
            getattr(mod, "append_entry")(
                args.name,
                status,
                args.summary or f"pytest_rc={rc}",
                args.expect,
                env={},
            )

    print(f"gate_status={status} pytest_rc={rc} missing={len(missing)}")
    if missing:
        for m in missing:
            print("missing:", m)
    raise SystemExit(0 if status == "pass" else 1)


if __name__ == "__main__":
    main()
