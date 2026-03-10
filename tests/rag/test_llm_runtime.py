from __future__ import annotations

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
