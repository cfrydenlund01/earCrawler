from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_phase5_training_runner_prepare_only_writes_manifest_and_metadata(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "retrieval_corpus.jsonl"
    corpus.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "section_id": "EAR-736.2(b)",
                        "doc_id": "EAR-736.2(b)",
                        "source_ref": "snapshot:test",
                        "text": "General prohibitions define when a license is required.",
                    }
                ),
                json.dumps(
                    {
                        "section_id": "EAR-740.1",
                        "doc_id": "EAR-740.1",
                        "source_ref": "snapshot:test",
                        "text": "License exceptions may authorize exports without a license.",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out_root = tmp_path / "dist_training"
    run_id = "phase5-test-run"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/training/run_phase5_finetune.py",
            "--prepare-only",
            "--retrieval-corpus",
            str(corpus),
            "--output-root",
            str(out_root),
            "--run-id",
            run_id,
            "--snapshot-id",
            "ecfr-title15-2026-02-28",
            "--snapshot-sha256",
            "abc123",
            "--max-examples",
            "4",
        ],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout

    run_dir = out_root / run_id
    manifest_path = run_dir / "manifest.json"
    examples_path = run_dir / "examples.jsonl"
    config_path = run_dir / "run_config.json"
    metadata_path = run_dir / "run_metadata.json"

    assert manifest_path.exists()
    assert examples_path.exists()
    assert config_path.exists()
    assert metadata_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "training-package.v1"
    assert manifest["base_model"] == "Qwen/Qwen2.5-7B-Instruct"
    assert manifest["example_count"] == 4
    assert metadata["status"] == "prepare_only"
    assert metadata["prepare_only"] is True
