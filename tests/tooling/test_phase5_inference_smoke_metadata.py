from __future__ import annotations

import sys
import types
from pathlib import Path

from scripts.training import run_phase5_finetune as phase5


class _FakeTensor:
    def to(self, _device: str) -> "_FakeTensor":
        return self


class _FakeCuda:
    @staticmethod
    def is_available() -> bool:
        return False

    @staticmethod
    def is_bf16_supported() -> bool:
        return False


class _FakeNoGrad:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeTorch:
    cuda = _FakeCuda()
    float16 = "float16"
    bfloat16 = "bfloat16"

    @staticmethod
    def no_grad() -> _FakeNoGrad:
        return _FakeNoGrad()


class _FakeTokenizer:
    pad_token = "<pad>"
    eos_token = "<eos>"
    pad_token_id = 0
    eos_token_id = 1

    @classmethod
    def from_pretrained(cls, _path: str, **_kwargs) -> "_FakeTokenizer":
        return cls()

    def __call__(self, _prompt: str, return_tensors: str = "pt") -> dict[str, _FakeTensor]:
        assert return_tensors == "pt"
        return {"input_ids": _FakeTensor(), "attention_mask": _FakeTensor()}

    def decode(self, _tokens, skip_special_tokens: bool = True) -> str:
        assert skip_special_tokens is True
        return "When is a license required under EAR section 736.2(b)? A license may be required."


class _FakeModel:
    device = "cpu"

    @classmethod
    def from_pretrained(cls, _base_model: str, **_kwargs) -> "_FakeModel":
        return cls()

    def eval(self) -> None:
        return None

    def generate(self, **_kwargs):
        return [[1, 2, 3]]


def test_phase5_inference_smoke_includes_base_model_and_adapter_dir(
    monkeypatch, tmp_path: Path
) -> None:
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        phase5,
        "_load_training_deps",
        lambda: (_FakeTorch, _FakeModel, _FakeTokenizer, None, None, None, None),
    )
    fake_peft = types.SimpleNamespace(
        PeftModel=types.SimpleNamespace(from_pretrained=lambda model, _adapter: model)
    )
    monkeypatch.setitem(sys.modules, "peft", fake_peft)

    result = phase5._run_inference_smoke(
        base_model="hf-internal-testing/tiny-random-LlamaForCausalLM",
        adapter_dir=adapter_dir,
        prompt="When is a license required under EAR section 736.2(b)?",
        max_new_tokens=32,
        allow_pt_bin=False,
    )

    assert result["base_model"] == "hf-internal-testing/tiny-random-LlamaForCausalLM"
    assert result["adapter_dir"] == str(adapter_dir)
    assert result["pass"] is True

