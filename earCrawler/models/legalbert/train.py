"""Training utilities for Legal-BERT using PEFT/LoRA.

This script performs two phases of training:

1. Pretraining with masked language modelling on an EAR corpus.
2. Fine-tuning for binary classification (controlled vs non-controlled).

Both phases make use of LoRA adapters and only the adapters are persisted
on disk. The training datasets are intentionally tiny so that this script
can run quickly during continuous integration. Replace ``load_ear_corpus``
and ``load_classification_dataset`` with real data loading logic for
practical use.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, TYPE_CHECKING

from earCrawler.utils.import_guard import import_optional

if TYPE_CHECKING:  # pragma: no cover - hints only
    import torch
    from transformers import AutoTokenizer
    from peft import LoraConfig

try:
    from torch.utils.data import Dataset
except ImportError:  # pragma: no cover - optional dependency

    class Dataset:  # type: ignore
        """Fallback Dataset base class used when torch is unavailable."""

        pass


# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------


class TextDataset(Dataset):
    """A minimal dataset backing :class:`~transformers.Trainer`.

    The dataset is pre-tokenised on initialisation so that __getitem__ simply
    slices tensors. This keeps the example lightweight and avoids bringing in
    the ``datasets`` dependency which keeps CI fast.
    """

    def __init__(
        self,
        texts: List[str],
        tokenizer: AutoTokenizer,
        labels: List[int] | None = None,
    ) -> None:
        torch_mod = import_optional("torch", ["torch"])
        encodings = tokenizer(
            texts, truncation=True, padding="max_length", max_length=64
        )
        self.encodings = {k: torch_mod.tensor(v) for k, v in encodings.items()}
        self.labels = labels
        self._torch = torch_mod

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.encodings["input_ids"])

    def __getitem__(self, idx: int) -> dict:
        item = {k: v[idx] for k, v in self.encodings.items()}
        if self.labels is not None:
            item["labels"] = self._torch.tensor(self.labels[idx])
        return item


def load_ear_corpus(tokenizer: AutoTokenizer) -> Dataset:
    """Return a tiny EAR corpus for quick masked LM training."""

    texts = [
        "The Export Administration Regulations control certain exports.",
        "Dual-use items may require a license under the EAR.",
    ] * 16  # duplicate to provide enough samples for a few batches
    return TextDataset(texts, tokenizer)


def load_classification_dataset(tokenizer: AutoTokenizer) -> Dataset:
    """Return a tiny dataset for controlled vs non-controlled classification."""

    texts = [
        "This component is controlled under the EAR.",
        "This general consumer product is not controlled.",
        "The part falls under controlled technology.",
        "This item is commercially available and unrestricted.",
    ]
    labels = [1, 0, 1, 0]
    return TextDataset(texts, tokenizer, labels)


# ---------------------------------------------------------------------------
# Training routines
# ---------------------------------------------------------------------------


def _build_lora_config() -> "LoraConfig":
    peft = import_optional("peft", ["peft"])
    return peft.LoraConfig(
        r=8,
        lora_alpha=32,
        target_modules=["query", "value"],
        lora_dropout=0.1,
        bias="none",
    )


def freeze_base_params(model: torch.nn.Module) -> None:
    """Freeze all parameters of the underlying base model."""

    for param in model.base_model.parameters():
        param.requires_grad = False


def run_pretraining(tokenizer: AutoTokenizer, do_train: bool, do_eval: bool) -> None:
    """Run masked language model pretraining and save the LoRA adapter."""

    transformers = import_optional("transformers", ["transformers"])
    peft = import_optional("peft", ["peft"])

    model = transformers.AutoModelForMaskedLM.from_pretrained("bert-base-uncased")
    freeze_base_params(model)
    model = peft.get_peft_model(model, _build_lora_config())

    dataset = load_ear_corpus(tokenizer)
    data_collator = transformers.DataCollatorForLanguageModeling(
        tokenizer=tokenizer, mlm_probability=0.15
    )
    output_dir = Path("models") / "legalbert" / "lora_pretrained"

    args = transformers.TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=3,
        per_device_train_batch_size=16,
        save_strategy="epoch",
        logging_steps=1,
        overwrite_output_dir=True,
        report_to=[],
        dataloader_pin_memory=False,
        label_names=["labels"],
    )

    trainer = transformers.Trainer(
        model=model,
        args=args,
        train_dataset=dataset,
        eval_dataset=dataset,
        data_collator=data_collator,
    )

    if do_train:
        trainer.train()
        model.save_pretrained(str(output_dir))
    if do_eval:
        trainer.evaluate()


def run_classification(tokenizer: AutoTokenizer, do_train: bool, do_eval: bool) -> None:
    """Fine-tune the classifier using the previously saved adapter."""

    transformers = import_optional("transformers", ["transformers"])
    peft = import_optional("peft", ["peft"])

    base_model = transformers.AutoModelForSequenceClassification.from_pretrained(
        "bert-base-uncased", num_labels=2
    )
    freeze_base_params(base_model)
    model = peft.get_peft_model(base_model, _build_lora_config())

    adapter_path = Path("models") / "legalbert" / "lora_pretrained"
    if adapter_path.exists():
        model.load_adapter(
            str(adapter_path), adapter_name="pretrained", is_trainable=True
        )
        # ``set_active_adapters`` was removed in favour of ``set_adapter`` in
        # recent versions of ``peft``. Using the newer API avoids an
        # AttributeError during fine-tuning.
        model.set_adapter("pretrained")

    dataset = load_classification_dataset(tokenizer)
    output_dir = Path("models") / "legalbert" / "lora_classification"

    args = transformers.TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=2,
        per_device_train_batch_size=16,
        save_strategy="epoch",
        logging_steps=1,
        overwrite_output_dir=True,
        report_to=[],
        dataloader_pin_memory=False,
        label_names=["labels"],
    )

    trainer = transformers.Trainer(
        model=model,
        args=args,
        train_dataset=dataset,
        eval_dataset=dataset,
        data_collator=transformers.default_data_collator,
    )

    if do_train:
        trainer.train()
        model.save_pretrained(str(output_dir))
    if do_eval:
        trainer.evaluate()


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Legal-BERT with LoRA adapters")
    parser.add_argument("--do_train", action="store_true", help="Run training")
    parser.add_argument("--do_eval", action="store_true", help="Run evaluation")
    args = parser.parse_args()

    transformers = import_optional("transformers", ["transformers"])
    tokenizer = transformers.AutoTokenizer.from_pretrained("bert-base-uncased")
    run_pretraining(tokenizer, args.do_train, args.do_eval)
    run_classification(tokenizer, args.do_train, args.do_eval)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
