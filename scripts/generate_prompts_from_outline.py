import argparse
import json
from pathlib import Path

BASE_HEADER = [
    "You are a senior coding agent working in this repo at the current working directory.",
    "Keep changes minimal, deterministic, and Windows-first.",
    "Reuse existing CLI/API/file contracts; do not break public interfaces.",
    "Validate via tests and local commands; avoid network in tests.",
    "Acceptance: all existing tests pass + new tests pass + commands run.",
]

KEY_FILES = {
    "kg": [
        "earCrawler/kg/ontology.py:1",
        "earCrawler/kg/shapes.ttl:1",
        "earCrawler/kg/shapes_prov.ttl:1",
        "earCrawler/kg/validate.py:1",
        "earCrawler/kg/emit_ear.py:1",
    ],
    "sparql_api": [
        "service/openapi/openapi.yaml:1",
        "service/api_server/routers/entities.py:1",
        "service/api_server/routers/search.py:1",
        "service/api_server/routers/sparql.py:1",
    ],
    "retrieval": [
        "earCrawler/rag/retriever.py:1",
        "earCrawler/agent/mistral_agent.py:1",
    ],
    "observability": [
        "docs/proposal/observability.md:1",
        "earCrawler/observability/*:1",
    ],
}

TEMPLATE = """
Base Header
- {base_header}

Goal
- {goal}

Scope
- {scope}

Key files
{key_files}

Deliverables
- {deliverables}

Acceptance criteria
- {acceptance}

Validation commands
{validation}

Non-goals
- {non_goals}
"""


def bullets(items):
    if isinstance(items, str):
        items = [items]
    return "\n".join(f"- {it}" for it in items)


def write_prompt(
    outdir: Path,
    name: str,
    goal: str,
    scope: list[str],
    key_files: list[str],
    deliverables: list[str],
    acceptance: list[str],
    validation_cmds: list[str],
    non_goals: list[str],
):
    outdir.mkdir(parents=True, exist_ok=True)
    content = TEMPLATE.format(
        base_header="\n- ".join(BASE_HEADER),
        goal=goal,
        scope="\n".join(f"- {s}" for s in scope),
        key_files="\n".join(f"- {p}" for p in key_files),
        deliverables="\n".join(f"- {d}" for d in deliverables),
        acceptance="\n".join(f"- {a}" for a in acceptance),
        validation="\n".join(f"- `{c}`" for c in validation_cmds),
        non_goals="\n".join(f"- {n}" for n in non_goals),
    )
    (outdir / f"{name}_prompt.txt").write_text(content, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(
        description="Generate GPT-5 Codex prompts from working_json_outline"
    )
    ap.add_argument("--outline", default="Research/working_json_outline.json")
    ap.add_argument("--outdir", default="Research/prompts")
    ap.add_argument("--all", action="store_true")
    ap.add_argument(
        "--target",
        choices=[
            "kg_shacl",
            "kg_temporal",
            "reasoning",
            "retrieval",
            "evaluation",
            "policy_graph",
        ],
    )
    args = ap.parse_args()

    outline_path = Path(args.outline)
    payload = json.loads(outline_path.read_text(encoding="utf-8"))
    w = payload.get("working_json_outline", payload)

    outdir = Path(args.outdir)

    def gen_policy_graph():
        goal = "Extend EAR ontology with policy-graph logic and enforce SHACL/temporal constraints."
        scope = [
            "Add node/edge vocab per outline; document in ontology",
            "Author SHACL shapes for obligations/exceptions/conditions",
            "Implement temporal constraint checks (EffectiveDate windows)",
            "Emit provenance links to spans and hashes",
        ]
        acceptance = [
            "Shapes validate fixture TTL; negative tests fail",
            "Temporal windows enforced in validation",
            "Ontology documented; no contract breaks",
        ]
        validation = [
            "pytest -q tests/kg",
            "py -m earCrawler.cli integrity check kg/ear.ttl",
        ]
        write_prompt(
            outdir,
            "policy_graph",
            goal,
            scope,
            KEY_FILES["kg"],
            ["Updated ontology+shapes", "Tests for SHACL/temporal"],
            acceptance,
            validation,
            ["Model training", "API surface changes"],
        )

    def gen_kg_shacl():
        shacl = (
            w.get("kg_construction", {})
            .get("policy_graph", {})
            .get("constraints", {})
            .get("shacl", [])
        )
        goal = "Add SHACL shapes capturing policy-graph constraints and wire to integrity checks."
        scope = [f"SHACL: {s}" for s in shacl] or [
            "Author SHACL shapes per policy-graph constraints"
        ]
        acceptance = [
            "All shapes conform on positive fixtures",
            "Violations reported with clear messages",
        ]
        validation = [
            "pytest -q tests/kg/test_shacl_entities.py tests/test_shacl_parts.py"
        ]
        write_prompt(
            outdir,
            "kg_shacl",
            goal,
            scope,
            KEY_FILES["kg"],
            ["shapes.ttl updates", "tests"],
            acceptance,
            validation,
            ["Temporal logic"],
        )

    def gen_kg_temporal():
        goal = "Implement temporal validation and query patterns for EffectiveDate windows."
        scope = [
            "Add temporal validation helper",
            "Update integrity checks",
            "Provide SPARQL examples",
        ]
        acceptance = [
            "Temporal constraints enforced on queries and TTL",
            "Tests cover edge cases",
        ]
        validation = ["pytest -q tests/kg"]
        write_prompt(
            outdir,
            "kg_temporal",
            goal,
            scope,
            KEY_FILES["kg"],
            ["temporal utils", "tests"],
            acceptance,
            validation,
            ["SHACL authoring"],
        )

    def gen_reasoning():
        templates = (
            w.get("kg_construction", {})
            .get("policy_graph", {})
            .get("reasoning_templates", [])
        )
        goal = "Implement reasoning templates over KG (obligations, permissions, procedures)"
        scope = [f"Implement template: {t}" for t in templates] or [
            "Implement obligation and exception chain templates"
        ]
        acceptance = [
            "Templates return correct paths on fixtures",
            "Explainability payload includes KG paths",
        ]
        validation = ["pytest -q tests/kg tests/test_lineage.py"]
        key_files = KEY_FILES["kg"] + KEY_FILES["sparql_api"]
        write_prompt(
            outdir,
            "reasoning_templates",
            goal,
            scope,
            key_files,
            ["SPARQL templates", "tests"],
            acceptance,
            validation,
            ["Model training"],
        )

    def gen_retrieval():
        r = w.get("retrieval_and_reasoning", {}).get("hybrid_retrieval", [])
        goal = (
            "Add hybrid retrieval with entity/date filters and optional dense fusion."
        )
        scope = r or [
            "BM25 retriever",
            "Dense encoder integration",
            "RRF fusion",
            "Caching and determinism",
        ]
        acceptance = [
            "Deterministic retrieval on fixtures",
            "Latency budgets documented",
        ]
        validation = ["pytest -q tests/rag/test_retriever.py"]
        write_prompt(
            outdir,
            "retrieval",
            goal,
            scope,
            KEY_FILES["retrieval"],
            ["retriever implementation", "tests"],
            acceptance,
            validation,
            ["Model finetuning"],
        )

    def gen_evaluation():
        bench = w.get("evaluation_and_explainability", {}).get("benchmarks", {})
        goal = "Build groundedness-first evaluation suite with failure-mode audits."
        scope = [
            "Task sets: " + ", ".join(bench.get("task_sets", [])),
            "Metrics: " + ", ".join(bench.get("groundedness_metrics", [])),
            "Quality metrics: " + ", ".join(bench.get("quality_metrics", [])),
            "Failure modes: " + ", ".join(bench.get("evaluator_failure_modes", [])),
        ]
        acceptance = w.get(
            "acceptance_criteria", ["Thresholds documented and enforced in tests"]
        )
        validation = ["pytest -q tests/perf tests/eval -q"]
        key_files = KEY_FILES["retrieval"] + KEY_FILES["kg"]
        write_prompt(
            outdir,
            "evaluation",
            goal,
            scope,
            key_files,
            ["eval harness", "fixtures", "reports"],
            acceptance,
            validation,
            ["Live API eval"],
        )

    if args.all or args.target is None:
        gen_policy_graph()
        gen_kg_shacl()
        gen_kg_temporal()
        gen_reasoning()
        gen_retrieval()
        gen_evaluation()
    else:
        {
            "kg_shacl": gen_kg_shacl,
            "kg_temporal": gen_kg_temporal,
            "reasoning": gen_reasoning,
            "retrieval": gen_retrieval,
            "evaluation": gen_evaluation,
            "policy_graph": gen_policy_graph,
        }[args.target]()


if __name__ == "__main__":
    main()
