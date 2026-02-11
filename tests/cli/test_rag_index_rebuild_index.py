from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from earCrawler.cli.__main__ import cli
from earCrawler.rag.snapshot_index import SnapshotIndexBundle


def _write_corpus(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    docs = [
        {
            "schema_version": "retrieval-corpus.v1",
            "doc_id": "EAR-736.2",
            "section_id": "EAR-736.2",
            "text": "General prohibitions text.",
            "chunk_kind": "section",
            "source": "ecfr_snapshot",
            "source_ref": "snap-1",
            "snapshot_id": "snap-test-cli",
            "snapshot_sha256": "a" * 64,
            "part": "736",
        }
    ]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for doc in docs:
            handle.write(json.dumps(doc, sort_keys=True) + "\n")


def test_rag_index_rebuild_index_cli_success(monkeypatch, tmp_path: Path) -> None:
    corpus_path = tmp_path / "retrieval_corpus.jsonl"
    _write_corpus(corpus_path)

    bundle = SnapshotIndexBundle(
        snapshot_id="snap-test-cli",
        index_dir=tmp_path / "dist" / "snap-test-cli",
        index_path=tmp_path / "dist" / "snap-test-cli" / "index.faiss",
        meta_path=tmp_path / "dist" / "snap-test-cli" / "index.meta.json",
        build_log_path=tmp_path / "dist" / "snap-test-cli" / "index_build_log.json",
        env_file_path=tmp_path / "dist" / "snap-test-cli" / "runtime.env",
        env_ps1_path=tmp_path / "dist" / "snap-test-cli" / "runtime_env.ps1",
        embedding_model="stub-model",
        corpus_digest="abc123",
        doc_count=1,
        build_timestamp_utc="2026-02-10T00:00:00Z",
        smoke_result_count=1,
        smoke_expected_hits=1,
    )

    def _stub_build_snapshot_index_bundle(**kwargs):
        return bundle

    import earCrawler.cli.__main__ as main_mod

    monkeypatch.setattr(main_mod, "build_snapshot_index_bundle", _stub_build_snapshot_index_bundle)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "rag-index",
            "rebuild-index",
            "--corpus",
            str(corpus_path),
            "--out-base",
            str(tmp_path / "dist"),
            "--model-name",
            "stub-model",
            "--smoke-query",
            "General prohibitions",
            "--expect-section",
            "EAR-736.2",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Wrote index:" in result.output
    assert "Index metadata verified:" in result.output
    assert "Retrieval smoke passed:" in result.output


def test_rag_index_rebuild_index_cli_fails_on_validation_error(monkeypatch, tmp_path: Path) -> None:
    corpus_path = tmp_path / "retrieval_corpus.jsonl"
    _write_corpus(corpus_path)

    def _stub_build_snapshot_index_bundle(**kwargs):
        raise ValueError("bad metadata")

    import earCrawler.cli.__main__ as main_mod

    monkeypatch.setattr(main_mod, "build_snapshot_index_bundle", _stub_build_snapshot_index_bundle)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "rag-index",
            "rebuild-index",
            "--corpus",
            str(corpus_path),
        ],
    )
    assert result.exit_code != 0
    assert "Error: bad metadata" in result.output
