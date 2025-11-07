"""Smoke tests for Legal-BERT LoRA adapters."""

from pathlib import Path

import importlib
import sys
import types
import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
peft = pytest.importorskip("peft")

BertConfig = transformers.BertConfig
BertForSequenceClassification = transformers.BertForSequenceClassification
LoraConfig = peft.LoraConfig
PeftModel = peft.PeftModel
get_peft_model = peft.get_peft_model


def test_classification_adapter_forward(tmp_path, monkeypatch) -> None:
    """Create a tiny adapter and ensure it loads and runs."""

    orig_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: None if name == "bitsandbytes" else orig_find_spec(name, *a, **k),
    )

    config = BertConfig(num_labels=2)
    base_model = BertForSequenceClassification(config)
    lora_config = LoraConfig(
        task_type="SEQ_CLS", r=2, lora_alpha=4, target_modules=["query", "value"]
    )
    model = get_peft_model(base_model, lora_config)
    model.save_pretrained(str(tmp_path))
    reloaded = PeftModel.from_pretrained(base_model, str(tmp_path))
    inputs = {"input_ids": torch.tensor([[0, 1]], dtype=torch.long)}
    outputs = reloaded(**inputs)
    assert outputs.logits.shape[-1] == 2
