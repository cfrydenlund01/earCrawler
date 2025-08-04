"""Smoke tests for Legal-BERT LoRA adapters."""

from pathlib import Path

from transformers import AutoModelForSequenceClassification, AutoTokenizer
from peft import PeftModel


def test_classification_adapter_forward() -> None:
    """Load the classification adapter and run a forward pass."""

    adapter_dir = Path("models") / "legalbert" / "lora_classification"
    tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
    base_model = AutoModelForSequenceClassification.from_pretrained(
        "bert-base-uncased", num_labels=2
    )
    model = PeftModel.from_pretrained(base_model, str(adapter_dir))
    inputs = tokenizer("dummy", return_tensors="pt")
    outputs = model(**inputs)
    assert outputs.logits.shape[-1] == 2
