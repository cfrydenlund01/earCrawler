"""Mistral QLoRA agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING, Protocol

from earCrawler.utils.import_guard import import_optional

Dataset = None  # type: ignore[assignment]
TrainingArguments = None  # type: ignore[assignment]
Trainer = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover - hints only
    from datasets import Dataset as HFDataset
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        Trainer,
        TrainingArguments,
    )
    from peft import LoraConfig, get_peft_model


if TYPE_CHECKING:  # pragma: no cover - imported for type checkers only
    from .long_context_pipeline import LongContextPipeline


class Retriever(Protocol):
    def query(self, query: str, k: int = ...) -> List[str]: ...


class LegalBERT(Protocol):
    def filter(self, query: str, contexts: List[str]) -> List[str]: ...


DEFAULT_MODEL = "mistralai/Mistral-7B-v0.1"
ADAPTER_DIR = Path("models/mistral7b/qlora_adapter")


def load_mistral_with_lora(
    model_name: str = DEFAULT_MODEL,
    use_4bit: bool = True,
):
    """Load Mistral-7B in 4-bit and attach a LoRA adapter.

    Parameters
    ----------
    model_name:
        Base model name on the Hugging Face hub.
    use_4bit:
        Whether to enable 4-bit quantization via ``bnb.QuantLinear``.
    """
    transformers = import_optional("transformers", ["transformers"])
    peft = import_optional("peft", ["peft"])

    quant_config = None
    if use_4bit:
        import_optional("bitsandbytes", ["bitsandbytes"])
        quant_config = transformers.BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )

    tokenizer = transformers.AutoTokenizer.from_pretrained(model_name)
    model = transformers.AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=quant_config,
        device_map="auto" if use_4bit else None,
    )

    lora_config = peft.LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = peft.get_peft_model(model, lora_config)
    return tokenizer, model


def train_qlora_adapter(
    model_name: str = DEFAULT_MODEL,
    output_dir: Path = ADAPTER_DIR,
    use_4bit: bool = True,
    trainer_cls=None,
) -> None:
    """Fine-tune the adapter weights using a small EAR dataset."""
    transformers = import_optional("transformers", ["transformers"])

    global Trainer
    if Trainer is None:
        Trainer = transformers.Trainer
    trainer_cls = trainer_cls or Trainer

    global TrainingArguments
    if TrainingArguments is None:
        TrainingArguments = transformers.TrainingArguments
    tokenizer, model = load_mistral_with_lora(model_name, use_4bit=use_4bit)

    global Dataset
    if Dataset is None:
        datasets = import_optional("datasets", ["datasets"])
        Dataset = datasets.Dataset
    data = Dataset.from_dict(  # type: ignore[union-attr]
        {
            "prompt": [
                "What does EAR regulate?",
                "Who enforces EAR?",
            ],
            "completion": [
                "EAR regulates the export of dual-use items.",
                "The U.S. Department of Commerce enforces EAR.",
            ],
        }
    )

    def _format(example):
        text = example["prompt"] + "\n" + example["completion"]
        tokens = tokenizer(text, truncation=True)
        tokens["labels"] = tokens["input_ids"].copy()
        return tokens

    train_ds = data.map(_format)

    args = TrainingArguments(
        output_dir=str(output_dir),
        per_device_train_batch_size=1,
        num_train_epochs=1,
        logging_steps=1,
        learning_rate=2e-4,
        report_to=[],
    )
    trainer = trainer_cls(model=model, train_dataset=train_ds, args=args)
    trainer.train()
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))


@dataclass
class Agent:
    """Retrieval-augmented generation agent using a QLoRA Mistral model."""

    retriever: "Retriever"
    legalbert: Optional["LegalBERT"] = None
    model: Optional[object] = None
    tokenizer: Optional[object] = None
    long_context_pipeline: Optional["LongContextPipeline"] = None

    def __post_init__(self) -> None:
        if self.model is None or self.tokenizer is None:
            self.tokenizer, self.model = load_mistral_with_lora()

    def _build_prompt(self, query: str, contexts: List[str]) -> str:
        context_block = "\n".join(contexts)
        system = (
            "You are an expert on Export Administration Regulations and answer"
            " user questions using the provided context."
        )
        user = f"Context:\n{context_block}\n\nQuestion: {query}\nAnswer:"
        return system + "\n\n" + user

    def _filter_contexts(self, query: str, contexts: List[str]) -> List[str]:
        """Apply the LegalBERT filter when available."""

        if self.legalbert is None:
            return contexts
        return self.legalbert.filter(query, contexts)

    def _summarize_contexts(self, contexts: List[str]) -> List[str]:
        """Summarize overly long contexts using the LED pipeline."""

        pipeline = self.long_context_pipeline
        if pipeline is None:
            return contexts

        summarized: List[str] = []
        for context in contexts:
            token_count = pipeline.count_long_document_tokens(context)
            if token_count > pipeline.chunk_token_length:
                summary = pipeline.summarize_long_document(context).strip()
                summarized.append(summary or context)
            else:
                summarized.append(context)
        return summarized

    def answer(self, query: str, k: int = 5) -> str:
        contexts = self.retriever.query(query, k=k)
        contexts = self._filter_contexts(query, contexts)
        contexts = self._summarize_contexts(contexts)
        prompt = self._build_prompt(query, contexts)
        inputs = self.tokenizer(prompt, return_tensors="pt")
        outputs = self.model.generate(**inputs, max_new_tokens=128)
        text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        return text
