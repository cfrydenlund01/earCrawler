from __future__ import annotations

import json

import pytest

from earCrawler.rag import llm_runtime


class _Provider:
    def __init__(self, *, provider: str = "groq", model: str = "llama") -> None:
        self.provider = provider
        self.model = model


class _Config:
    def __init__(self, *, enable_remote: bool, disabled_reason: str | None = None) -> None:
        self.provider = _Provider()
        self.enable_remote = enable_remote
        self.remote_disabled_reason = disabled_reason
        self.enable_local = False
        self.local_disabled_reason = None
        self.execution_mode = "remote"



def test_resolve_llm_request_raises_with_egress_when_remote_disabled() -> None:
    prompt = llm_runtime.build_prompt_artifacts(
        "What applies?",
        ["[EAR-740.1] License Exceptions intro."],
    )

    with pytest.raises(llm_runtime.LLMExecutionError) as exc_info:
        llm_runtime.resolve_llm_request(
            prompt,
            trace_id="trace-1",
            get_llm_config_fn=lambda **_: _Config(
                enable_remote=False,
                disabled_reason="remote LLM policy denied egress",
            ),
        )

    exc = exc_info.value
    assert exc.error_code == "llm_disabled"
    assert exc.disabled_reason == "remote LLM policy denied egress"
    assert exc.egress_decision.remote_enabled is False
    assert exc.egress_decision.provider == "groq"



def test_validate_generated_answer_reports_schema_errors_without_provider_failure() -> None:
    prompt = llm_runtime.build_prompt_artifacts(
        "What applies?",
        ["[EAR-740.1] License Exceptions intro."],
    )
    egress = llm_runtime.ResolvedLLMRequest(
        provider_label="groq",
        model_label="llama",
        prompt_artifacts=prompt,
    ).build_egress_decision(
        remote_enabled=True,
        disabled_reason=None,
        trace_id="trace-2",
    )

    result = llm_runtime.validate_generated_answer(
        "plain text",
        prompt_artifacts=prompt,
        provider_label="groq",
        model_label="llama",
        egress_decision=egress,
        strict_output=True,
        empty_collections_on_error=False,
    )

    assert result.llm_enabled is True
    assert result.llm_attempted is True
    assert result.output_ok is False
    assert result.output_error["code"] == "invalid_json"
    assert result.answer_text is None
    assert result.provider_label == "groq"


def test_resolve_llm_request_raises_when_local_adapter_disabled() -> None:
    prompt = llm_runtime.build_prompt_artifacts(
        "What applies?",
        ["[EAR-740.1] License Exceptions intro."],
    )

    class _LocalConfig:
        def __init__(self) -> None:
            self.provider = type(
                "_Provider",
                (),
                {
                    "provider": "local_adapter",
                    "model": "phase5-run",
                    "base_model": "google/gemma-4-E4B-it",
                    "adapter_dir": "dist/training/phase5-run/adapter",
                },
            )()
            self.enable_remote = False
            self.remote_disabled_reason = "local adapter provider selected"
            self.enable_local = False
            self.local_disabled_reason = "local LLM flag is off; set EARCRAWLER_ENABLE_LOCAL_LLM=1"
            self.execution_mode = "local"

    with pytest.raises(llm_runtime.LLMExecutionError) as exc_info:
        llm_runtime.resolve_llm_request(
            prompt,
            trace_id="trace-local-disabled",
            get_llm_config_fn=lambda **_: _LocalConfig(),
        )

    exc = exc_info.value
    assert exc.error_code == "llm_disabled"
    assert exc.provider_label == "local_adapter"
    assert exc.model_label == "phase5-run"
    assert exc.egress_decision.remote_enabled is False
    assert "EARCRAWLER_ENABLE_LOCAL_LLM=1" in exc.disabled_reason


def test_validate_generated_answer_recovers_local_adapter_invalid_json() -> None:
    prompt = llm_runtime.build_prompt_artifacts(
        "Do laptops to France need a license?",
        ["[EAR-742.6] A license is required for listed ECCNs."],
    )
    egress = llm_runtime.ResolvedLLMRequest(
        provider_label="local_adapter",
        model_label="phase5-run",
        prompt_artifacts=prompt,
        execution_mode="local",
    ).build_egress_decision(
        remote_enabled=False,
        disabled_reason=None,
        trace_id="trace-local-fallback",
    )

    result = llm_runtime.validate_generated_answer(
        '{"label":"unanswerable","answer_text":"Cannot determine',
        prompt_artifacts=prompt,
        provider_label="local_adapter",
        model_label="phase5-run",
        egress_decision=egress,
        strict_output=True,
        empty_collections_on_error=True,
    )

    assert result.output_ok is True
    assert result.output_error is None
    assert result.label == "unanswerable"
    assert isinstance(result.answer_text, str)
    assert "Need " in result.answer_text
    assert result.raw_answer is not None


def test_execute_sync_generation_uses_local_adapter_without_remote_egress(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    run_dir = tmp_path / "phase5-run"
    adapter_dir = run_dir / "adapter"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
    (adapter_dir / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    (run_dir / "run_metadata.json").write_text("{}", encoding="utf-8")
    (run_dir / "inference_smoke.json").write_text(
        json.dumps({"base_model": "google/gemma-4-E4B-it"}),
        encoding="utf-8",
    )

    prompt = llm_runtime.build_prompt_artifacts(
        "Question?",
        ["[EAR-740.1] License Exceptions intro"],
    )

    class _LocalConfig:
        def __init__(self) -> None:
            self.provider = type(
                "_Provider",
                (),
                {
                    "provider": "local_adapter",
                    "model": "phase5-run",
                    "base_model": "google/gemma-4-E4B-it",
                    "adapter_dir": str(adapter_dir),
                },
            )()
            self.enable_remote = False
            self.remote_disabled_reason = "local adapter provider selected"
            self.enable_local = True
            self.local_disabled_reason = None
            self.execution_mode = "local"

    called = {"remote": False}

    def _fail_remote(*_args, **_kwargs):
        called["remote"] = True
        raise AssertionError("Remote generate_chat should not run for local adapter path")

    monkeypatch.setattr(
        llm_runtime,
        "generate_local_chat",
        lambda *_args, **_kwargs: (
            '{'
            '"label":"permitted",'
            '"answer_text":"Yes",'
            '"citations":[{"section_id":"EAR-740.1","quote":"License Exceptions intro","span_id":""}],'
            '"evidence_okay":{"ok":true,"reasons":["citation_quote_is_substring_of_context"]},'
            '"assumptions":[]'
            '}'
        ),
    )

    result = llm_runtime.execute_sync_generation(
        prompt,
        strict_output=True,
        trace_id="trace-local",
        generate_chat_fn=_fail_remote,
        get_llm_config_fn=lambda **_: _LocalConfig(),
        empty_collections_on_error=False,
    )

    assert called["remote"] is False
    assert result.output_ok is True
    assert result.answer_text == "Yes"
    assert result.provider_label == "local_adapter"
    assert result.model_label == "phase5-run"
    assert result.egress_decision.remote_enabled is False

