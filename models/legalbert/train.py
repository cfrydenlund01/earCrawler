import argparse
from pathlib import Path

import torch
from torch.utils.data import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForMaskedLM,
    AutoModelForSequenceClassification,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
    default_data_collator,
)
from peft import LoraConfig, get_peft_model, PeftModel, TaskType


class TextDataset(Dataset):
    """Simple dataset for MLM pretraining."""

    def __init__(self, texts, tokenizer, max_length: int = 128):
        self.examples = [
            tokenizer(
                t,
                truncation=True,
                padding="max_length",
                max_length=max_length,
            )
            for t in texts
        ]

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        item = {k: torch.tensor(v) for k, v in self.examples[idx].items()}
        return item


class ClassificationDataset(Dataset):
    """Simple dataset for sequence classification."""

    def __init__(self, texts, labels, tokenizer, max_length: int = 128):
        self.examples = [
            tokenizer(
                t,
                truncation=True,
                padding="max_length",
                max_length=max_length,
            )
            for t in texts
        ]
        self.labels = labels

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        item = {k: torch.tensor(v) for k, v in self.examples[idx].items()}
        item["labels"] = torch.tensor(self.labels[idx])
        return item


def freeze_base_model(model: torch.nn.Module) -> None:
    base = getattr(model, model.base_model_prefix, None)
    if base is not None:
        for param in base.parameters():
            param.requires_grad = False


def run_pretraining(tokenizer, output_dir: Path, do_train: bool, do_eval: bool) -> None:
    texts = [
        "Export Administration Regulations govern dual-use items.",
        "The Commerce Control List enumerates controlled technologies.",
    ]
    dataset = TextDataset(texts, tokenizer)
    model = AutoModelForMaskedLM.from_pretrained("bert-base-uncased")
    freeze_base_model(model)
    lora_config = LoraConfig(
        r=8,
        lora_alpha=32,
        target_modules=["query", "value"],
        lora_dropout=0.1,
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer, mlm=True, mlm_probability=0.15
    )
    args_kwargs = dict(
        output_dir=str(output_dir),
        overwrite_output_dir=True,
        per_device_train_batch_size=16,
        num_train_epochs=3,
        logging_steps=1,
    )
    if "save_strategy" in TrainingArguments.__init__.__code__.co_varnames:
        args_kwargs["save_strategy"] = "no"
    if "evaluation_strategy" in TrainingArguments.__init__.__code__.co_varnames:
        args_kwargs["evaluation_strategy"] = "epoch" if do_eval else "no"
    args = TrainingArguments(**args_kwargs)
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=dataset,
        eval_dataset=dataset if do_eval else None,
        data_collator=data_collator,
    )
    if do_train:
        trainer.train()
        model.save_pretrained(str(output_dir))
    if do_eval:
        trainer.evaluate()


def run_classification(
    tokenizer,
    pretrained_dir: Path,
    output_dir: Path,
    do_train: bool,
    do_eval: bool,
) -> None:
    texts = [
        "Controlled technology requires a license to export.",
        "The team played soccer at the park.",
    ]
    labels = [1, 0]
    dataset = ClassificationDataset(texts, labels, tokenizer)
    model = AutoModelForSequenceClassification.from_pretrained(
        "bert-base-uncased", num_labels=2
    )
    freeze_base_model(model)
    model = PeftModel.from_pretrained(
        model, str(pretrained_dir), is_trainable=True
    )
    # ensure classification head is trainable
    if hasattr(model, "classifier"):
        for param in model.classifier.parameters():
            param.requires_grad = True
    args_kwargs = dict(
        output_dir=str(output_dir),
        overwrite_output_dir=True,
        per_device_train_batch_size=16,
        num_train_epochs=2,
        logging_steps=1,
    )
    if "save_strategy" in TrainingArguments.__init__.__code__.co_varnames:
        args_kwargs["save_strategy"] = "no"
    if "evaluation_strategy" in TrainingArguments.__init__.__code__.co_varnames:
        args_kwargs["evaluation_strategy"] = "epoch" if do_eval else "no"
    args = TrainingArguments(**args_kwargs)
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=dataset,
        eval_dataset=dataset if do_eval else None,
        data_collator=default_data_collator,
    )
    if do_train:
        trainer.train()
        model.save_pretrained(str(output_dir))
    if do_eval:
        trainer.evaluate()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--do_train", action="store_true")
    parser.add_argument("--do_eval", action="store_true")
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")

    base_path = Path("models") / "legalbert"
    pretrain_dir = base_path / "lora_pretrained"
    cls_dir = base_path / "lora_classification"
    pretrain_dir.mkdir(parents=True, exist_ok=True)
    cls_dir.mkdir(parents=True, exist_ok=True)

    run_pretraining(tokenizer, pretrain_dir, args.do_train, args.do_eval)
    run_classification(tokenizer, pretrain_dir, cls_dir, args.do_train, args.do_eval)


if __name__ == "__main__":
    main()
