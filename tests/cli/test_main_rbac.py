from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from earCrawler.cli import cli


POLICY_PATH = Path(__file__).resolve().parents[2] / "security" / "policy.yml"


def _invoke(args: list[str], *, user: str, audit_dir: Path) -> object:
    runner = CliRunner()
    return runner.invoke(
        cli,
        args,
        env={
            "EARCTL_USER": user,
            "EARCTL_POLICY_PATH": str(POLICY_PATH),
            "EARCTL_AUDIT_DIR": str(audit_dir),
            "EARCTL_AUDIT_RUN_ID": "",
        },
    )


def _audit_entries(audit_dir: Path) -> list[dict]:
    files = sorted(audit_dir.rglob("*.jsonl"))
    assert files, "expected an audit log file"
    entries: list[dict] = []
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
    return entries


def test_fetch_ear_denies_reader_and_audits(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    result = _invoke(["fetch-ear", "--term", "export"], user="test_reader", audit_dir=audit_dir)

    assert result.exit_code != 0
    assert "requires role(s): operator" in result.output
    entry = _audit_entries(audit_dir)[-1]
    assert entry["event"] == "denied"
    assert entry["command"] == "fetch-ear"


def test_fetch_ear_allows_operator_and_audits(monkeypatch, tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    monkeypatch.setattr("earCrawler.cli.ear_fetch.FederalRegisterClient", lambda: object())
    monkeypatch.setattr(
        "earCrawler.cli.ear_fetch.fetch_ear_corpus",
        lambda term, *, client, out_dir: None,
    )

    result = _invoke(["fetch-ear", "--term", "export"], user="test_operator", audit_dir=audit_dir)

    assert result.exit_code == 0, result.output
    entry = _audit_entries(audit_dir)[-1]
    assert entry["event"] == "command"
    assert entry["command"] == "fetch-ear"
    assert entry["exit_code"] == 0


def test_telemetry_status_requires_operator_and_audits(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    denied = _invoke(["telemetry", "status"], user="test_reader", audit_dir=audit_dir)
    assert denied.exit_code != 0
    assert "command 'telemetry' requires role(s): operator" in denied.output
    denied_entry = _audit_entries(audit_dir)[-1]
    assert denied_entry["event"] == "denied"
    assert denied_entry["command"] == "telemetry"

    allowed = _invoke(["telemetry", "status"], user="test_operator", audit_dir=audit_dir)
    assert allowed.exit_code == 0, allowed.output
    allowed_entry = _audit_entries(audit_dir)[-1]
    assert allowed_entry["event"] == "command"
    assert allowed_entry["command"] == "telemetry"


def test_crawl_requires_operator(monkeypatch, tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"

    class DummyLoader:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def run(self, **kwargs) -> list[dict]:
            return [{"id": "p1"}]

    monkeypatch.setattr("earCrawler.core.nsf_loader.NSFLoader", DummyLoader)
    monkeypatch.setattr("earCrawler.core.nsf_case_parser.NSFCaseParser", lambda: object())

    denied = _invoke(
        ["crawl", "--sources", "nsf", "--fixtures", str(tmp_path)],
        user="test_reader",
        audit_dir=audit_dir,
    )
    assert denied.exit_code != 0
    assert "command 'crawl' requires role(s): operator" in denied.output

    allowed = _invoke(
        ["crawl", "--sources", "nsf", "--fixtures", str(tmp_path)],
        user="test_operator",
        audit_dir=audit_dir,
    )
    assert allowed.exit_code == 0, allowed.output


def test_kg_serve_requires_operator_or_maintainer_and_audits(monkeypatch, tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    monkeypatch.setattr(
        "earCrawler.kg.fuseki.build_fuseki_cmd",
        lambda db, dataset, port, java_opts: ["fuseki-server", "--port", str(port)],
    )

    denied = _invoke(["kg-serve", "--dry-run"], user="test_reader", audit_dir=audit_dir)
    assert denied.exit_code != 0
    assert "command 'kg-serve' requires role(s): operator, maintainer" in denied.output

    allowed = _invoke(["kg-serve", "--dry-run"], user="test_operator", audit_dir=audit_dir)
    assert allowed.exit_code == 0, allowed.output
    entry = _audit_entries(audit_dir)[-1]
    assert entry["event"] == "command"
    assert entry["command"] == "kg-serve"


def test_eval_verify_evidence_requires_operator_or_maintainer(monkeypatch, tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    corpus_path = tmp_path / "corpus.jsonl"
    corpus_path.write_text(
        json.dumps(
            {
                "id": "EAR-740.1",
                "section": "740.1",
                "text": "License Exceptions intro",
                "source_url": "http://example/740",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "id": "item-1",
                "ear_sections": ["EAR-740.1"],
                "evidence": {"doc_spans": [{"doc_id": "EAR-740", "span_id": "740.1"}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"datasets": [{"id": "ds1", "file": str(dataset_path)}]}),
        encoding="utf-8",
    )

    denied = _invoke(
        ["eval", "verify-evidence", "--manifest", str(manifest_path), "--corpus", str(corpus_path)],
        user="test_reader",
        audit_dir=audit_dir,
    )
    assert denied.exit_code != 0
    assert "command 'eval' requires role(s): operator, maintainer" in denied.output

    allowed = _invoke(
        ["eval", "verify-evidence", "--manifest", str(manifest_path), "--corpus", str(corpus_path)],
        user="test_operator",
        audit_dir=audit_dir,
    )
    assert allowed.exit_code == 0, allowed.output
    entry = _audit_entries(audit_dir)[-1]
    assert entry["event"] == "command"
    assert entry["command"] == "eval"


def test_kg_query_allows_reader_and_audits(monkeypatch, tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"

    class DummyClient:
        def __init__(self, endpoint: str) -> None:
            self.endpoint = endpoint

        def select(self, query: str) -> dict:
            return {"results": {"bindings": []}}

    monkeypatch.setattr("earCrawler.cli.__main__.SPARQLClient", DummyClient)
    out_path = tmp_path / "rows.json"

    result = _invoke(
        ["kg-query", "--sparql", "SELECT * WHERE { ?s ?p ?o } LIMIT 1", "--out", str(out_path)],
        user="test_reader",
        audit_dir=audit_dir,
    )

    assert result.exit_code == 0, result.output
    assert out_path.exists()
    entry = _audit_entries(audit_dir)[-1]
    assert entry["event"] == "command"
    assert entry["command"] == "kg-query"
