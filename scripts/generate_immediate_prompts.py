from pathlib import Path

BASE_HEADER = (
    "You are a senior coding agent working in this repo at the current working directory.\n"
    "Keep changes minimal, deterministic, and Windows-first.\n"
    "Reuse existing CLI/API/file contracts; do not break public interfaces.\n"
    "Validate via tests and local commands; avoid network in tests.\n"
    "Acceptance: all existing tests pass + new tests pass + commands run."
)

IMMEDIATE = [
    {
        "name": "immediate_phase_a_hardening",
        "goal": "Harden Phase A corpus pipeline (dedupe/merge, provenance, PII redaction, snapshots, operator run summaries).",
        "scope": [
            "Add/ensure corpus CLI group: corpus {build,validate,snapshot}",
            "Dedupe by sha256 across sources; stable sort and checksums",
            "Enforce provenance (sha256, source_url, date, provider)",
            "Apply PII redaction to paragraph text (email/tokens/ids/paths/queries/phone/SSN)",
            "Write manifest + checksums + run summaries",
        ],
        "key_files": [
            "earCrawler/core/ear_loader.py:1",
            "earCrawler/core/nsf_loader.py:1",
            "earCrawler/core/ear_crawler.py:1",
            "earCrawler/transforms/canonical.py:1",
            "earCrawler/transforms/mentions.py:1",
            "earCrawler/analytics/reports.py:1",
            "earCrawler/kg/emit_ear.py:1",
            "earCrawler/cli/__main__.py:1",
            "earCrawler/cli/jobs.py:1",
            "docs/privacy/redaction_rules.md:1",
        ],
        "deliverables": [
            "earCrawler/cli/corpus.py (group + commands)",
            "Data outputs: data/*_corpus.jsonl, data/manifest.json, data/checksums.sha256",
            "Unit tests: tests/corpus/*, tests/privacy/*, tests/cli/test_corpus_cli.py",
        ],
        "acceptance": [
            "Deterministic outputs and checksums",
            "Dedupe respected; provenance present; redaction applied",
            "Jobs call corpus build+validate before bundle/emit",
        ],
        "validation": [
            "pytest -q tests/corpus tests/privacy tests/cli",
            "py -m earCrawler.cli corpus build -s ear -s nsf --fixtures tests/fixtures --out data",
            "py -m earCrawler.cli corpus validate --dir data",
            "py -m earCrawler.cli corpus snapshot --dir data --out dist/corpus/20250101",
        ],
        "non_goals": ["Ontology/SHACL changes", "Model training", "RAG changes"],
    },
    {
        "name": "immediate_phase_b_baseline",
        "goal": "Freeze v1 ontology/shapes; verify export profiles; add SPARQL perf warmers + budgets.",
        "scope": [
            "Version shapes and ontology; document migration notes",
            "Export profiles with manifest+hash verification in CI",
            "Warm SPARQL queries; add latency budgets in tests",
        ],
        "key_files": [
            "earCrawler/kg/ontology.py:1",
            "earCrawler/kg/shapes.ttl:1",
            "earCrawler/kg/shapes_prov.ttl:1",
            "earCrawler/kg/export_profiles.py:1",
            "perf/warmers/warm_queries.json:1",
            "RUNBOOK.md:1",
        ],
        "deliverables": [
            "Frozen shapes/ontology + notes",
            "Export manifest/hash verification hooks",
            "Perf tests asserting latency budgets",
        ],
        "acceptance": [
            "Exports verified; hashes stable",
            "SPARQL latency budgets pass locally",
        ],
        "validation": [
            "pytest -q tests/bundle tests/perf",
        ],
        "non_goals": ["API/RAG changes", "Model training"],
    },
    {
        "name": "immediate_api_rag_touchpoint",
        "goal": "Align OpenAPI; add minimal RAG endpoint stub with traces, caching, and source/lineage payload.",
        "scope": [
            "Update/confirm service/openapi/openapi.yaml for RAG endpoint",
            "Implement endpoint using existing retriever; add trace IDs and cache hooks",
            "Return sources, scores, and optional KG lineage references",
        ],
        "key_files": [
            "service/openapi/openapi.yaml:1",
            "service/api_server/routers/search.py:1",
            "service/api_server/routers/entities.py:1",
            "service/api_server/routers/sparql.py:1",
            "service/api_server/logging_integration.py:1",
            "earCrawler/rag/retriever.py:1",
        ],
        "deliverables": [
            "RAG endpoint stub + docs",
            "Integration tests for contract and latency",
        ],
        "acceptance": [
            "Contracts stable; latency budget documented",
            "Responses include trace IDs and source/lineage fields",
        ],
        "validation": [
            "pytest -q tests/rag tests/service -q",
        ],
        "non_goals": ["Model fine-tuning", "New ranking models"],
    },
    {
        "name": "immediate_packaging_ops",
        "goal": "Dry-run release scripts; verify signed wheel/EXE/installer and SBOM generation.",
        "scope": [
            "Build wheel/EXE/installer with existing scripts",
            "Generate checksums and SBOM; verify signatures",
            "Update RUNBOOK, ensure Windows-first instructions",
        ],
        "key_files": [
            "RUNBOOK.md:1",
            "installer/earcrawler.iss:1",
            "bundle/static/SBOM.cdx.json:1",
        ],
        "deliverables": [
            "Built artifacts (local) + verification logs",
            "Updated runbook as needed",
        ],
        "acceptance": [
            "Signatures verify locally",
            "Checksums/SBOM generated and match",
        ],
        "validation": [
            "pwsh scripts/build-wheel.ps1",
            "pwsh scripts/build-exe.ps1",
            "pwsh scripts/make-installer.ps1",
            "pwsh scripts/sign-artifacts.ps1",
            "pwsh scripts/checksums.ps1",
            "pwsh scripts/sbom.ps1",
        ],
        "non_goals": ["CI release", "Publishing"],
    },
]

PROMPT_FMT = (
    "Base Header\n- {base}\n\n"
    "Goal\n- {goal}\n\n"
    "Scope\n{scope}\n\n"
    "Key files\n{key_files}\n\n"
    "Deliverables\n{deliverables}\n\n"
    "Acceptance criteria\n{acceptance}\n\n"
    "Validation commands\n{validation}\n\n"
    "Non-goals\n{non_goals}\n"
)

outdir = Path('Research/prompts')
outdir.mkdir(parents=True, exist_ok=True)

for item in IMMEDIATE:
    content = PROMPT_FMT.format(
        base=BASE_HEADER.replace('\n', '\n- '),
        goal=item['goal'],
        scope='\n'.join(f'- {s}' for s in item['scope']),
        key_files='\n'.join(f'- {p}' for p in item['key_files']),
        deliverables='\n'.join(f'- {d}' for d in item['deliverables']),
        acceptance='\n'.join(f'- {a}' for a in item['acceptance']),
        validation='\n'.join(f'- `{c}`' for c in item['validation']),
        non_goals='\n'.join(f'- {n}' for n in item['non_goals']),
    )
    (outdir / f"{item['name']}_prompt.txt").write_text(content, encoding='utf-8')

print('Generated immediate prompts in', outdir)
