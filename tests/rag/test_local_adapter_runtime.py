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


class _FakeTensor(list):
    @property
    def shape(self) -> tuple[int, int]:
        return (1, len(self[0]))

    def to(self, _device: str) -> "_FakeTensor":
        return self


class _FakeTokenizer:
    eos_token = ""
    eos_token_id = 99

    def __call__(self, _prompt: str, return_tensors: str = "pt") -> dict[str, _FakeTensor]:
        assert return_tensors == "pt"
        return {"input_ids": _FakeTensor([[1, 2, 3]])}

    def decode(self, _tokens, skip_special_tokens: bool = True) -> str:
        assert skip_special_tokens is True
        return "generated answer"


class _FakeModel:
    device = "cpu"

    def __init__(self) -> None:
        self.generate_kwargs: dict[str, object] | None = None

    def generate(self, **kwargs):
        assert local_adapter_runtime._LOCAL_GENERATION_LOCK.locked() is True
        self.generate_kwargs = kwargs
        return [[1, 2, 3, 4, 5]]

    def eval(self) -> None:
        return None


class _RetryTokenizer(_FakeTokenizer):
    def __init__(self, outputs: dict[tuple[int, ...], str]) -> None:
        self._outputs = outputs

    def decode(self, tokens, skip_special_tokens: bool = True) -> str:
        assert skip_special_tokens is True
        return self._outputs[tuple(tokens)]


class _RetryModel:
    device = "cpu"

    def __init__(self) -> None:
        self.calls: list[int] = []

    def generate(self, **kwargs):
        self.calls.append(int(kwargs["max_new_tokens"]))
        if len(self.calls) == 1:
            return [[1, 2, 3, 101]]
        return [[1, 2, 3, 102]]

    def eval(self) -> None:
        return None


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
    cfg = _provider_cfg(base_model="google/gemma-4-E4B-it", adapter_dir=adapter_dir)
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
    cfg = _provider_cfg(base_model="google/gemma-4-E4B-it", adapter_dir=adapter_dir)
    with pytest.raises(LLMProviderError, match="base model mismatch"):
        local_adapter_runtime.resolve_local_adapter_artifacts(cfg)


def test_resolve_generation_limits_defaults(monkeypatch) -> None:
    monkeypatch.delenv("EARCRAWLER_LOCAL_LLM_MAX_NEW_TOKENS", raising=False)
    monkeypatch.delenv("EARCRAWLER_LOCAL_LLM_MAX_TIME_SECONDS", raising=False)

    max_new_tokens, max_time = local_adapter_runtime._resolve_generation_limits()

    assert max_new_tokens == 64
    assert max_time == 20.0


def test_generate_local_chat_applies_generation_limits(monkeypatch) -> None:
    fake_model = _FakeModel()
    fake_tokenizer = _FakeTokenizer()

    monkeypatch.setenv("EARCRAWLER_LOCAL_LLM_MAX_NEW_TOKENS", "96")
    monkeypatch.setenv("EARCRAWLER_LOCAL_LLM_MAX_TIME_SECONDS", "12.5")
    monkeypatch.setattr(
        local_adapter_runtime,
        "resolve_local_adapter_artifacts",
        lambda _provider_cfg: local_adapter_runtime.LocalAdapterArtifacts(
            adapter_dir=Path("adapter"),
            run_dir=Path("run"),
            base_model="google/gemma-4-E4B-it",
            model_label="run-1",
        ),
    )
    monkeypatch.setattr(local_adapter_runtime, "_resolve_device_name", lambda: "cpu")
    monkeypatch.setattr(
        local_adapter_runtime,
        "_load_local_stack",
        lambda *_args: (fake_tokenizer, fake_model, ""),
    )

    result = local_adapter_runtime.generate_local_chat(
        [{"role": "user", "content": "Q?"}],
        provider_cfg=ProviderConfig(
            provider="local_adapter",
            api_key="",
            model="run-1",
            base_url="",
            base_model="google/gemma-4-E4B-it",
            adapter_dir="adapter",
            execution_mode="local",
        ),
    )

    assert result == "generated answer"
    assert fake_model.generate_kwargs is not None
    assert fake_model.generate_kwargs["max_new_tokens"] == 96
    assert fake_model.generate_kwargs["max_time"] == 12.5
    assert fake_model.generate_kwargs["do_sample"] is False
    assert fake_model.generate_kwargs["pad_token_id"] == 99


def test_generate_local_chat_retries_once_for_truncated_json(monkeypatch) -> None:
    retry_model = _RetryModel()
    retry_tokenizer = _RetryTokenizer(
        outputs={
            (101,): '{"label":"unanswerable","answer_text":"Cannot determine',
            (
                102,
            ): '{"label":"unanswerable","answer_text":"Insufficient information to determine. Need ECCN.","citations":[],"evidence_okay":{"ok":true,"reasons":["no_grounded_quote_for_key_claim"]},"assumptions":[]}',
        }
    )

    monkeypatch.setenv("EARCRAWLER_LOCAL_LLM_MAX_NEW_TOKENS", "64")
    monkeypatch.setenv("EARCRAWLER_LOCAL_LLM_JSON_RETRY_MAX_NEW_TOKENS", "160")
    monkeypatch.setattr(
        local_adapter_runtime,
        "resolve_local_adapter_artifacts",
        lambda _provider_cfg: local_adapter_runtime.LocalAdapterArtifacts(
            adapter_dir=Path("adapter"),
            run_dir=Path("run"),
            base_model="google/gemma-4-E4B-it",
            model_label="run-1",
        ),
    )
    monkeypatch.setattr(local_adapter_runtime, "_resolve_device_name", lambda: "cpu")
    monkeypatch.setattr(
        local_adapter_runtime,
        "_load_local_stack",
        lambda *_args: (retry_tokenizer, retry_model, ""),
    )

    result = local_adapter_runtime.generate_local_chat(
        [{"role": "user", "content": "Q?"}],
        provider_cfg=ProviderConfig(
            provider="local_adapter",
            api_key="",
            model="run-1",
            base_url="",
            base_model="google/gemma-4-E4B-it",
            adapter_dir="adapter",
            execution_mode="local",
        ),
        require_valid_json=True,
    )

    assert json.loads(result)["label"] == "unanswerable"
    assert retry_model.calls == [64, 160]


def test_generate_local_chat_skips_json_retry_without_explicit_override(
    monkeypatch,
) -> None:
    retry_model = _RetryModel()
    retry_tokenizer = _RetryTokenizer(
        outputs={(101,): '{"label":"unanswerable","answer_text":"Cannot determine'}
    )

    monkeypatch.setenv("EARCRAWLER_LOCAL_LLM_MAX_NEW_TOKENS", "64")
    monkeypatch.delenv(
        "EARCRAWLER_LOCAL_LLM_JSON_RETRY_MAX_NEW_TOKENS",
        raising=False,
    )
    monkeypatch.delenv(
        "EARCRAWLER_LOCAL_LLM_JSON_RETRY_MAX_TIME_SECONDS",
        raising=False,
    )
    monkeypatch.setattr(
        local_adapter_runtime,
        "resolve_local_adapter_artifacts",
        lambda _provider_cfg: local_adapter_runtime.LocalAdapterArtifacts(
            adapter_dir=Path("adapter"),
            run_dir=Path("run"),
            base_model="google/gemma-4-E4B-it",
            model_label="run-1",
        ),
    )
    monkeypatch.setattr(local_adapter_runtime, "_resolve_device_name", lambda: "cpu")
    monkeypatch.setattr(
        local_adapter_runtime,
        "_load_local_stack",
        lambda *_args: (retry_tokenizer, retry_model, ""),
    )

    result = local_adapter_runtime.generate_local_chat(
        [{"role": "user", "content": "Q?"}],
        provider_cfg=ProviderConfig(
            provider="local_adapter",
            api_key="",
            model="run-1",
            base_url="",
            base_model="google/gemma-4-E4B-it",
            adapter_dir="adapter",
            execution_mode="local",
        ),
        require_valid_json=True,
    )

    assert result == '{"label":"unanswerable","answer_text":"Cannot determine'
    assert retry_model.calls == [64]

