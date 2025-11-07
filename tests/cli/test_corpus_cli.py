from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from earCrawler.cli.corpus import corpus


def test_corpus_cli_build_validate_and_snapshot(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    repo_root = Path(__file__).resolve().parents[2]
    fixtures = repo_root / "tests" / "fixtures"
    monkeypatch.chdir(tmp_path)

    build_result = runner.invoke(
        corpus,
        ["build", "-s", "ear", "-s", "nsf", "--out", "data", "--fixtures", str(fixtures)],
    )
    assert build_result.exit_code == 0, build_result.output
    data_dir = tmp_path / "data"
    assert (data_dir / "ear_corpus.jsonl").exists()

    validate_result = runner.invoke(corpus, ["validate", "--dir", "data"])
    assert validate_result.exit_code == 0, validate_result.output

    snapshot_result = runner.invoke(
        corpus,
        ["snapshot", "--dir", "data", "--out", "snapshots"],
    )
    assert snapshot_result.exit_code == 0, snapshot_result.output
    snapshots = list((tmp_path / "snapshots").iterdir())
    assert snapshots, "snapshot folder should be created"


def test_corpus_validate_cli_fails_on_bad_data(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "ear_corpus.jsonl").write_text("{}", encoding="utf-8")

    result = runner.invoke(corpus, ["validate", "--dir", "data"])
    assert result.exit_code != 0
