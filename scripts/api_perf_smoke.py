from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from earCrawler.perf.api_budget_gate import main


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
