from __future__ import annotations

"""Local adapter-backed generation helpers for the optional Phase 5.4 runtime path."""

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

from api_clients.llm_client import LLMProviderError
from earCrawler.config.llm_secrets import ProviderConfig


@dataclass(frozen=True)
class LocalAdapterArtifacts:
    adapter_dir: Path
    run_dir: Path
    base_model: str
    model_label: str


def _chat_prompt_text(messages: Sequence[dict[str, str]], tokenizer: Any) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        return str(
            tokenizer.apply_chat_template(
                list(messages),
                tokenize=False,
                add_generation_prompt=True,
            )
        )
    return "\n\n".join(
        f"{str(message.get('role') or 'user').upper()}:\n{str(message.get('content') or '')}"
        for message in messages
    )


def _require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise LLMProviderError(f"Missing local adapter {label}: {path}")


def resolve_local_adapter_artifacts(provider_cfg: ProviderConfig) -> LocalAdapterArtifacts:
    adapter_dir = Path(str(provider_cfg.adapter_dir or "")).expanduser().resolve()
    if not str(provider_cfg.base_model or "").strip():
        raise LLMProviderError(
            "Local adapter base model is not configured. Set EARCRAWLER_LOCAL_LLM_BASE_MODEL."
        )
    if not adapter_dir.exists():
        raise LLMProviderError(
            f"Local adapter directory not found: {adapter_dir}. "
            "Set EARCRAWLER_LOCAL_LLM_ADAPTER_DIR to a Task 5.3 adapter artifact."
        )
    _require_file(adapter_dir / "adapter_config.json", "adapter_config.json")
    _require_file(adapter_dir / "tokenizer_config.json", "tokenizer_config.json")

    run_dir = adapter_dir.parent
    _require_file(run_dir / "run_metadata.json", "run_metadata.json")
    _require_file(run_dir / "inference_smoke.json", "inference_smoke.json")

    smoke_report = json.loads((run_dir / "inference_smoke.json").read_text(encoding="utf-8"))
    smoke_base_model = str(smoke_report.get("base_model") or "").strip()
    if smoke_base_model and smoke_base_model != str(provider_cfg.base_model).strip():
        raise LLMProviderError(
            "Local adapter base model mismatch between runtime config and inference_smoke.json "
            f"({provider_cfg.base_model!r} != {smoke_base_model!r})."
        )

    return LocalAdapterArtifacts(
        adapter_dir=adapter_dir,
        run_dir=run_dir,
        base_model=str(provider_cfg.base_model).strip(),
        model_label=str(provider_cfg.model or run_dir.name).strip() or "local-adapter",
    )


@lru_cache(maxsize=2)
def _load_local_stack(
    base_model: str,
    adapter_dir: str,
    device_name: str,
) -> tuple[Any, Any, str]:
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:  # pragma: no cover - depends on optional extras
        raise LLMProviderError(
            "Local adapter inference requires torch, transformers, and peft. "
            "Install the optional GPU/runtime extras before enabling LLM_PROVIDER=local_adapter."
        ) from exc

    adapter_path = Path(adapter_dir)
    tokenizer = AutoTokenizer.from_pretrained(str(adapter_path), trust_remote_code=True)

    model_kwargs: dict[str, Any] = {"trust_remote_code": True}
    quantization_config = None
    if device_name == "cuda":
        if getattr(torch.cuda, "is_available", lambda: False)():
            try:
                from transformers import BitsAndBytesConfig
            except ImportError as exc:  # pragma: no cover - defensive guard
                raise LLMProviderError(
                    "BitsAndBytes is required for local adapter CUDA inference. "
                    "Install the optional GPU/runtime extras before enabling local adapters."
                ) from exc

            dtype = (
                torch.bfloat16
                if getattr(torch.cuda, "is_bf16_supported", lambda: False)()
                else torch.float16
            )
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=dtype,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
            model_kwargs["quantization_config"] = quantization_config
            model_kwargs["device_map"] = "auto"
            model_kwargs["low_cpu_mem_usage"] = True
        else:
            raise LLMProviderError(
                "EARCRAWLER_LOCAL_LLM_DEVICE=cuda requested but CUDA is not available."
            )

    model = AutoModelForCausalLM.from_pretrained(base_model, **model_kwargs)
    model = PeftModel.from_pretrained(model, str(adapter_path))
    if device_name == "cuda":
        model = model.to("cuda")
    model.eval()
    eos_token = tokenizer.eos_token or ""
    return tokenizer, model, eos_token


def _resolve_device_name() -> str:
    requested = str(os.getenv("EARCRAWLER_LOCAL_LLM_DEVICE", "auto")).strip().lower()
    if requested in {"cpu", "cuda"}:
        return requested
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if getattr(torch.cuda, "is_available", lambda: False)() else "cpu"


def _resolve_generation_limits() -> tuple[int, float | None]:
    max_new_tokens = max(32, int(os.getenv("EARCRAWLER_LOCAL_LLM_MAX_NEW_TOKENS", "64")))
    raw_max_time = str(os.getenv("EARCRAWLER_LOCAL_LLM_MAX_TIME_SECONDS", "20")).strip()
    if not raw_max_time:
        return max_new_tokens, None
    try:
        max_time = float(raw_max_time)
    except ValueError as exc:  # pragma: no cover - defensive env guard
        raise LLMProviderError(
            "EARCRAWLER_LOCAL_LLM_MAX_TIME_SECONDS must be a positive number."
        ) from exc
    if max_time <= 0:
        return max_new_tokens, None
    return max_new_tokens, max_time


def generate_local_chat(
    messages: Sequence[dict[str, str]],
    *,
    provider_cfg: ProviderConfig,
) -> str:
    artifacts = resolve_local_adapter_artifacts(provider_cfg)
    device_name = _resolve_device_name()
    tokenizer, model, eos_token = _load_local_stack(
        artifacts.base_model,
        str(artifacts.adapter_dir),
        device_name,
    )
    prompt_text = _chat_prompt_text(messages, tokenizer)
    max_new_tokens, max_time = _resolve_generation_limits()

    inputs = tokenizer(prompt_text, return_tensors="pt")
    if hasattr(model, "device"):
        inputs = {key: value.to(model.device) for key, value in inputs.items()}
    generate_kwargs: dict[str, Any] = {
        "do_sample": False,
        "max_new_tokens": max_new_tokens,
        "pad_token_id": getattr(tokenizer, "eos_token_id", None),
    }
    if max_time is not None:
        generate_kwargs["max_time"] = max_time
    try:
        import torch
    except ImportError:  # pragma: no cover - optional dependency guard
        torch = None

    if torch is not None and hasattr(torch, "inference_mode"):
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                **generate_kwargs,
            )
    else:
        generated = model.generate(
            **inputs,
            **generate_kwargs,
        )
    prompt_len = int(inputs["input_ids"].shape[-1])
    continuation = generated[0][prompt_len:]
    text = str(tokenizer.decode(continuation, skip_special_tokens=True)).strip()
    if not text and eos_token:
        text = eos_token
    if not text:
        raise LLMProviderError("Local adapter returned an empty response.")
    return text


__all__ = [
    "LocalAdapterArtifacts",
    "generate_local_chat",
    "resolve_local_adapter_artifacts",
]
