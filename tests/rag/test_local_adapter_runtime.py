from __future__ import annotations

import json
from pathlib import Path

import pytest

from api_clients.llm_client import LLMProviderError
from earCrawler.config.llm_secrets import ProviderConfig
from earCrawler.rag import local_adapter_runtime


def _provider_cfg(*, base_model: str, adapter_dir: Path | str) -> ProviderConfig:
    return ProviderConfig(
        provider="local_adapter",
        model="phase5-local",
        base_url="http://localhost/v1",
        api_key="",
        base_model=base_model,
        adapter_dir=str(adapter_dir),
    )


def test_resolve_local_adapter_artifacts_requires_base_model(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "run" / "adapter"
    adapter_dir.mkdir(parents=True)
    cfg = _provider_cfg(base_model="", adapter_dir=adapter_dir)
    with pytest.raises(LLMProviderError, match="base model is not configured"):
        local_adapter_runtime.resolve_local_adapter_artifacts(cfg)


def test_resolve_local_adapter_artifacts_requires_expected_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    adapter_dir = run_dir / "adapter"
    adapter_dir.mkdir(parents=True)
    cfg = _provider_cfg(base_model="Qwen/Qwen2.5-7B-Instruct", adapter_dir=adapter_dir)
    with pytest.raises(LLMProviderError, match="adapter_config.json"):
        local_adapter_runtime.resolve_local_adapter_artifacts(cfg)


def test_resolve_local_adapter_artifacts_rejects_base_model_mismatch(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    adapter_dir = run_dir / "adapter"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
    (adapter_dir / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    (run_dir / "run_metadata.json").write_text("{}", encoding="utf-8")
    (run_dir / "inference_smoke.json").write_text(
        json.dumps({"base_model": "meta-llama/Llama-3.1-8B-Instruct"}),
        encoding="utf-8",
    )
    cfg = _provider_cfg(base_model="Qwen/Qwen2.5-7B-Instruct", adapter_dir=adapter_dir)
    with pytest.raises(LLMProviderError, match="base model mismatch"):
        local_adapter_runtime.resolve_local_adapter_artifacts(cfg)
