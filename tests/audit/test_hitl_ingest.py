from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from earCrawler.audit import ledger
from earCrawler.audit.hitl_events import ingest_hitl_directory
from earCrawler.cli.__main__ import cli


def _allow_operator(monkeypatch) -> None:
    monkeypatch.setenv("EARCTL_USER", "test_operator")
    policy_path = (
        Path(__file__).resolve().parents[2] / "security" / "policy.yml"
    )
    monkeypatch.setenv("EARCTL_POLICY_PATH", str(policy_path))


def test_hitl_ingest_writes_ledger_and_summary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EARCTL_AUDIT_DIR", str(tmp_path / "audit"))
    templates = tmp_path / "hitl"
    templates.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "trace_id": "trace-1",
            "dataset_id": "multihop_slice.v1",
            "item_id": "mh-1",
            "question_hash": "q1",
            "initial_label": "true",
            "initial_answer_hash": "a1",
            "final_label": "true",
            "override": False,
            "time_to_decision_ms": 1000,
            "reason_code": "other",
            "provenance_hash": "1" * 64,
        },
        {
            "trace_id": "trace-2",
            "dataset_id": "multihop_slice.v1",
            "item_id": "mh-2",
            "question_hash": "q2",
            "initial_label": "false",
            "initial_answer_hash": "a2",
            "final_label": "true",
            "override": True,
            "time_to_decision_ms": 3000,
            "reason_code": "wrong_citation",
            "provenance_hash": "2" * 64,
        },
    ]
    for i, row in enumerate(rows, start=1):
        (templates / f"item-{i}.json").write_text(json.dumps(row), encoding="utf-8")

    summary = ingest_hitl_directory(templates)
    assert summary["ingested_events"] == 2
    assert summary["override_rate"] == 0.5
    assert summary["avg_time_to_decision_ms"] == 2000
    assert summary["top_reason_codes"][0]["reason_code"] in {"other", "wrong_citation"}

    entries = list(ledger.tail(10))
    hitl_entries = [entry for entry in entries if entry.get("event") == "hitl_decision"]
    assert len(hitl_entries) == 2
    assert hitl_entries[0]["payload"]["trace_id"] == "trace-1"


def test_audit_ingest_hitl_cli(monkeypatch, tmp_path: Path) -> None:
    _allow_operator(monkeypatch)
    monkeypatch.setenv("EARCTL_AUDIT_DIR", str(tmp_path / "audit"))
    templates = tmp_path / "hitl"
    templates.mkdir(parents=True, exist_ok=True)
    payload = {
        "trace_id": "trace-1",
        "dataset_id": "multihop_slice.v1",
        "item_id": "mh-1",
        "question_hash": "q1",
        "initial_label": "true",
        "initial_answer_hash": "a1",
        "final_label": "true",
        "override": False,
        "time_to_decision_ms": 1000,
        "reason_code": "other",
        "provenance_hash": "1" * 64,
    }
    (templates / "item-1.json").write_text(json.dumps(payload), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["audit", "ingest-hitl", str(templates)])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output.strip())
    assert summary["ingested_events"] == 1
    assert summary["override_rate"] == 0.0

