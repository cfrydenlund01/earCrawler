import argparse
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

try:  # pragma: no cover - optional
    import psutil
except Exception:  # pragma: no cover
    psutil = None  # type: ignore

from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Spin up FastAPI services using TestClient. Environment variables are set to
# dummy values so the apps can initialise without contacting external
# endpoints.
# ---------------------------------------------------------------------------
os.environ.setdefault("SPARQL_ENDPOINT_URL", "http://example.org/sparql")
os.environ.setdefault(
    "SHAPES_FILE_PATH", str(Path("earCrawler/ontology/shapes.ttl").resolve())
)

# Ensure repository root on sys.path for imports when executed from scripts/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # pragma: no cover - defensive
    sys.path.insert(0, str(ROOT))

# Stub heavy optional dependency before importing agent module
import importlib.machinery
import types

if "bitsandbytes" not in sys.modules:
    dummy = types.ModuleType("bitsandbytes")
    dummy.__spec__ = importlib.machinery.ModuleSpec("bitsandbytes", loader=None)
    dummy.nn = types.SimpleNamespace(Linear4bit=object)
    sys.modules["bitsandbytes"] = dummy

if "datasets" not in sys.modules:
    ds = types.ModuleType("datasets")
    ds.__spec__ = importlib.machinery.ModuleSpec("datasets", loader=None)
    ds.Dataset = object
    sys.modules["datasets"] = ds

if "peft" not in sys.modules:
    peft_mod = types.ModuleType("peft")
    peft_mod.__spec__ = importlib.machinery.ModuleSpec("peft", loader=None)
    peft_mod.LoraConfig = object
    peft_mod.get_peft_model = lambda *a, **k: object()
    peft_mod.PeftModel = object
    sys.modules["peft"] = peft_mod

from earCrawler.service.kg_service import app as kg_app  # noqa: E402
from earCrawler.service.sparql_service import app as analytics_app  # noqa: E402

kg_client = TestClient(kg_app)
analytics_client = TestClient(analytics_app)


# ---------------------------------------------------------------------------
# Lightweight stand-in implementations for the retriever, LegalBERT classifier
# and Mistral agent. These mimic the interfaces of the real components while
# keeping dependencies small so the benchmark can run quickly in CI.
# ---------------------------------------------------------------------------
class DummyRetriever:
    """Return canned contexts for a query."""

    def query(self, query: str, k: int = 5) -> List[str]:  # noqa: D401
        return [f"Context about {query}"] * k


class DummyLegalBERT:
    """Mock LegalBERT classifier using simple keyword rules."""

    label = "EAR"

    def classify(self, query: str, contexts: List[str]) -> List[str]:  # noqa: D401
        return [self.label for _ in contexts]

    def filter(self, query: str, contexts: List[str]) -> List[str]:  # noqa: D401
        return contexts


class DummyTokenizer:
    def __call__(self, text: str, return_tensors: str | None = None):  # noqa: D401
        return {"input_ids": [[0, 1, 2]]}

    def decode(self, ids, skip_special_tokens: bool = True):  # noqa: D401
        return "dummy answer"


class DummyModel:
    def generate(self, **kwargs):  # noqa: D401
        return [[0, 1, 2]]


from earCrawler.agent.mistral_agent import Agent  # noqa: E402


# ---------------------------------------------------------------------------
def load_queries(path: Path) -> List[Dict[str, Any]]:
    """Load benchmark queries from a JSON or YAML file."""

    if path.suffix.lower() in {".yml", ".yaml"} and yaml is not None:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Run end-to-end benchmark")
    parser.add_argument(
        "--queries",
        type=Path,
        default=Path("scripts/benchmark_queries.json"),
        help="Path to JSON/YAML file containing benchmark queries.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/benchmark_results.csv"),
        help="Destination for results CSV.",
    )
    args = parser.parse_args()

    queries = load_queries(args.queries)

    retriever = DummyRetriever()
    legalbert = DummyLegalBERT()
    agent = Agent(
        retriever=retriever,
        legalbert=legalbert,
        model=DummyModel(),
        tokenizer=DummyTokenizer(),
    )

    process = psutil.Process() if psutil else None

    records: List[Dict[str, Any]] = []
    for q in queries:
        query = q["query"]
        expected = q.get("expected", "")

        start = time.perf_counter()
        contexts = retriever.query(query)
        retrieval_latency = time.perf_counter() - start

        start = time.perf_counter()
        labels = legalbert.classify(query, contexts)
        classification_latency = time.perf_counter() - start

        start = time.perf_counter()
        answer = agent.answer(query)
        generation_latency = time.perf_counter() - start

        hit = expected.lower() in answer.lower() if expected else False
        memory = process.memory_info().rss / (1024**2) if process else 0.0

        records.append(
            {
                "query": query,
                "expected": expected,
                "answer": answer,
                "retrieval_hits": len(contexts),
                "classification": ",".join(labels),
                "hit": hit,
                "retrieval_latency": retrieval_latency,
                "classification_latency": classification_latency,
                "generation_latency": generation_latency,
                "memory_mb": memory,
            }
        )

    avg_retrieval = statistics.mean(r["retrieval_latency"] for r in records)
    avg_classification = statistics.mean(r["classification_latency"] for r in records)
    avg_generation = statistics.mean(r["generation_latency"] for r in records)
    accuracy = statistics.mean(r["hit"] for r in records)

    out_path = args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(records[0].keys())
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
        writer.writerow(
            {
                "query": "AVERAGE",
                "expected": "",
                "answer": "",
                "retrieval_hits": "",
                "classification": "",
                "hit": accuracy,
                "retrieval_latency": avg_retrieval,
                "classification_latency": avg_classification,
                "generation_latency": avg_generation,
                "memory_mb": "",
            }
        )
    print(f"Benchmark complete. Results saved to {out_path}")


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
