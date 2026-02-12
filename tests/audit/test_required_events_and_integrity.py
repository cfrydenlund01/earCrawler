from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from earCrawler.audit import ledger
from earCrawler.audit import required_events as audit_required_events
from earCrawler.cli.__main__ import cli
from scripts.eval import eval_rag_llm


def _allow_operator(monkeypatch) -> None:
    monkeypatch.setenv("EARCTL_USER", "test_operator")
    policy_path = Path(__file__).resolve().parents[2] / "security" / "policy.yml"
    monkeypatch.setenv("EARCTL_POLICY_PATH", str(policy_path))


def _stub_eval_llm(monkeypatch) -> None:
    class _Provider:
        provider = "stub"
        model = "stub-model"
        api_key = ""
        base_url = "https://example.invalid"
        request_limit = None

    class _Cfg:
        provider = _Provider()
        enable_remote = True

    monkeypatch.setattr(eval_rag_llm, "get_llm_config", lambda *a, **k: _Cfg())


def test_eval_pipeline_emits_minimum_required_audit_events(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EARCTL_AUDIT_DIR", str(tmp_path / "audit"))
    monkeypatch.setenv("EARCRAWLER_REFUSE_ON_THIN_RETRIEVAL", "1")
    monkeypatch.setenv("EARCRAWLER_REMOTE_LLM_POLICY", "allow")
    monkeypatch.setenv("EARCRAWLER_ENABLE_REMOTE_LLM", "1")
    monkeypatch.setenv("EARCRAWLER_SKIP_LLM_SECRETS_FILE", "1")
    _stub_eval_llm(monkeypatch)

    index_path = tmp_path / "index.faiss"
    index_path.write_bytes(b"tiny-index")
    meta_path = index_path.with_suffix(".meta.json")
    meta_path.write_text(
        json.dumps(
            {
                "schema_version": "retrieval-index.v1",
                "build_timestamp_utc": "2026-01-01T00:00:00+00:00",
                "embedding_model": "all-MiniLM-L12-v2",
                "corpus_digest": "c" * 64,
                "snapshot": {
                    "snapshot_id": "snap-test-1",
                    "snapshot_sha256": "s" * 64,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EARCRAWLER_FAISS_INDEX", str(index_path))
    monkeypatch.setenv("EARCRAWLER_FAISS_MODEL", "all-MiniLM-L12-v2")

    from earCrawler.rag import pipeline

    monkeypatch.setattr(pipeline, "retrieve_regulation_context", lambda *_a, **_k: [])
    monkeypatch.setattr(pipeline, "expand_with_kg", lambda *_a, **_k: [])
    monkeypatch.setattr(
        pipeline,
        "generate_chat",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("generate_chat must not run for thin retrieval refusal")
        ),
    )

    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "id": "item-1",
                "task": "ear_compliance",
                "question": "Can you decide this from no evidence?",
                "ground_truth": {
                    "answer_text": "Insufficient evidence to answer.",
                    "label": "unanswerable",
                },
                "ear_sections": [],
                "kg_entities": [],
                "evidence": {"doc_spans": [], "kg_nodes": []},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"datasets": [{"id": "ds.min", "file": str(dataset_path), "version": 1}]}),
        encoding="utf-8",
    )

    out_json = tmp_path / "dist" / "ds.min.rag.stub.json"
    out_md = tmp_path / "dist" / "ds.min.rag.stub.md"
    eval_rag_llm.evaluate_dataset(
        "ds.min",
        manifest_path=manifest_path,
        llm_provider="stub",
        llm_model="stub-model",
        top_k=1,
        max_items=1,
        out_json=out_json,
        out_md=out_md,
        answer_score_mode="semantic",
        semantic_threshold=0.6,
        semantic=False,
    )

    run_id = eval_rag_llm._safe_name(out_json.stem)
    ledger_path = ledger.current_log_path(run_id=run_id)
    report = audit_required_events.verify_required_events(
        ledger_path,
        scope="ci_eval",
        run_id=run_id,
    )
    assert report["ok"] is True, report

    entries = audit_required_events.filter_entries(
        audit_required_events.read_ledger_entries(ledger_path),
        run_id=run_id,
    )
    events = {str(entry.get("event") or "") for entry in entries}
    assert "query_refused" in events
    assert "remote_llm_policy_decision" in events
    assert "snapshot_selected" in events

    snapshot_payload = next(
        (entry.get("payload") for entry in entries if entry.get("event") == "snapshot_selected"),
        {},
    )
    assert isinstance(snapshot_payload, dict)
    assert snapshot_payload.get("snapshot_id") == "snap-test-1"
    assert snapshot_payload.get("snapshot_sha256") == "s" * 64

    policy_payload = next(
        (
            entry.get("payload")
            for entry in reversed(entries)
            if entry.get("event") == "remote_llm_policy_decision"
        ),
        {},
    )
    assert isinstance(policy_payload, dict)
    assert policy_payload.get("outcome") in {"allow", "deny"}
    assert policy_payload.get("outcome") == "deny"
    serialized_payload = json.dumps(policy_payload).lower()
    assert "api_key" not in serialized_payload
    assert "authorization" not in serialized_payload

    missing_event_path = tmp_path / "missing_query_outcome.jsonl"
    missing_entries = [entry for entry in entries if entry.get("event") != "query_refused"]
    missing_event_path.write_text(
        "\n".join(json.dumps(entry, ensure_ascii=False) for entry in missing_entries) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="query_outcome"):
        audit_required_events.assert_required_events(
            missing_event_path,
            scope="ci_eval",
            run_id=run_id,
        )


def test_ledger_integrity_check_reports_first_broken_link(monkeypatch, tmp_path: Path) -> None:
    _allow_operator(monkeypatch)
    monkeypatch.setenv("EARCTL_AUDIT_DIR", str(tmp_path / "audit"))
    run_id = "integrity-demo"
    for idx in range(3):
        ledger.append_fact(
            "demo_event",
            {"run_id": run_id, "idx": idx + 1},
            run_id=run_id,
        )
    source_path = ledger.current_log_path(run_id=run_id)

    good_report = ledger.verify_chain_report(source_path)
    assert good_report["ok"] is True
    assert int(good_report["checked_entries"]) == 3

    tampered_path = tmp_path / "tampered.jsonl"
    rows = [json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines()]
    rows[1]["payload"]["idx"] = 999  # tamper content without recomputing hashes
    tampered_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    bad_report = ledger.verify_chain_report(tampered_path)
    assert bad_report["ok"] is False
    assert bad_report["line"] == 2
    assert bad_report["reason"] == "chain_hash_mismatch"

    runner = CliRunner()
    result = runner.invoke(cli, ["audit", "verify", "--path", str(tampered_path)])
    assert result.exit_code != 0
    cli_report = json.loads(result.output.splitlines()[0])
    assert cli_report["ok"] is False
    assert cli_report["line"] == 2
    assert cli_report["reason"] == "chain_hash_mismatch"
