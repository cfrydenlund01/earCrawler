import subprocess
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForMaskedLM, AutoModelForSequenceClassification
from peft import PeftModel

TRAIN_SCRIPT = Path("models/legalbert/train.py")


def setup_module(module):
    subprocess.run(["python", str(TRAIN_SCRIPT), "--do_train"], check=True)


def test_lora_adapters_forward():
    tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
    inputs = tokenizer("export control", return_tensors="pt")

    mlm_model = AutoModelForMaskedLM.from_pretrained("bert-base-uncased")
    mlm_model = PeftModel.from_pretrained(mlm_model, Path("models/legalbert/lora_pretrained"))
    with torch.no_grad():
        out = mlm_model(**inputs)
    assert out.logits.shape[-1] == tokenizer.vocab_size

    cls_model = AutoModelForSequenceClassification.from_pretrained("bert-base-uncased", num_labels=2)
    cls_model = PeftModel.from_pretrained(cls_model, Path("models/legalbert/lora_classification"))
    with torch.no_grad():
        logits = cls_model(**inputs).logits
    assert logits.shape[-1] == 2
