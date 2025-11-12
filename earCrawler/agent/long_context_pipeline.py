"""Long-context conversational and summarization pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, TYPE_CHECKING

from earCrawler.utils.import_guard import import_optional

if TYPE_CHECKING:  # pragma: no cover - hints only
    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoModelForSeq2SeqLM,
        AutoTokenizer,
    )

LOGGER = logging.getLogger(__name__)

DEFAULT_CONVERSATION_MODEL = "mistralai/Mistral-7B-Instruct-v0.2"
DEFAULT_LONG_DOCUMENT_MODEL = "allenai/led-large-16384"


def _resolve_device(preferred: Optional[str] = None) -> "torch.device":
    """Return a torch device honoring CUDA availability."""

    torch = import_optional("torch", ["torch"])
    if preferred is not None:
        return torch.device(preferred)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


@dataclass
class LongContextPipeline:
    """Pipeline combining a 32k-context LLM with hierarchical summarization."""

    conversation_model_name: str = DEFAULT_CONVERSATION_MODEL
    long_document_model_name: str = DEFAULT_LONG_DOCUMENT_MODEL
    max_long_document_tokens: int = 16_384
    chunk_token_length: int = 14_336
    chunk_overlap: int = 512
    summary_max_length: int = 1_024
    summary_num_beams: int = 4

    conversation_tokenizer: AutoTokenizer = field(init=False)
    conversation_model: AutoModelForCausalLM = field(init=False)
    long_document_tokenizer: AutoTokenizer = field(init=False)
    long_document_model: AutoModelForSeq2SeqLM = field(init=False)
    long_document_device: torch.device = field(init=False)

    def __post_init__(self) -> None:
        self._load_conversation_model()
        self._load_long_document_model()

    def _load_conversation_model(self) -> None:
        """Load the 32k-context conversational model and tokenizer."""

        torch = import_optional("torch", ["torch"])
        transformers = import_optional("transformers", ["transformers"])
        AutoTokenizer = transformers.AutoTokenizer
        AutoModelForCausalLM = transformers.AutoModelForCausalLM

        LOGGER.info("Loading conversation model: %%s", self.conversation_model_name)
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        self.conversation_tokenizer = AutoTokenizer.from_pretrained(
            self.conversation_model_name
        )
        if self.conversation_tokenizer.pad_token is None:
            self.conversation_tokenizer.pad_token = (
                self.conversation_tokenizer.eos_token
            )
        self.conversation_model = AutoModelForCausalLM.from_pretrained(
            self.conversation_model_name,
            device_map="auto",
            torch_dtype=torch_dtype,
        )
        self.conversation_model.config.max_position_embeddings = max(
            getattr(self.conversation_model.config, "max_position_embeddings", 0),
            32_768,
        )
        # Ensure inference-only mode for performance and memory
        try:
            self.conversation_model.eval()
        except Exception:
            pass

    def _load_long_document_model(self) -> None:
        """Load the LED model used for long document summarization."""

        torch = import_optional("torch", ["torch"])
        transformers = import_optional("transformers", ["transformers"])
        AutoTokenizer = transformers.AutoTokenizer
        AutoModelForSeq2SeqLM = transformers.AutoModelForSeq2SeqLM

        LOGGER.info("Loading long document model: %%s", self.long_document_model_name)
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        self.long_document_tokenizer = AutoTokenizer.from_pretrained(
            self.long_document_model_name
        )
        if self.long_document_tokenizer.pad_token is None:
            self.long_document_tokenizer.pad_token = (
                self.long_document_tokenizer.eos_token
            )
        self.long_document_tokenizer.model_max_length = self.max_long_document_tokens
        self.long_document_model = AutoModelForSeq2SeqLM.from_pretrained(
            self.long_document_model_name,
            torch_dtype=torch_dtype,
        )
        self.long_document_model.config.max_position_embeddings = max(
            getattr(self.long_document_model.config, "max_position_embeddings", 0),
            self.max_long_document_tokens,
        )
        self.long_document_device = _resolve_device()
        self.long_document_model.to(self.long_document_device)
        try:
            self.long_document_model.eval()
        except Exception:
            pass

    def _conversation_device(self) -> "torch.device":
        """Return the device used by the conversational model."""

        torch = import_optional("torch", ["torch"])
        if hasattr(self.conversation_model, "hf_device_map"):
            device_map = getattr(self.conversation_model, "hf_device_map")
            if isinstance(device_map, dict):
                first_device = next(iter(device_map.values()))
                if isinstance(first_device, str):
                    return torch.device(first_device)
        try:
            return next(self.conversation_model.parameters()).device
        except StopIteration:  # pragma: no cover
            return torch.device("cpu")

    def generate_conversation_reply(
        self, prompt: str, max_new_tokens: int = 512
    ) -> str:
        """Generate a reply with the primary 32k-context LLM."""

        inputs = self.conversation_tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=32_000,
        )
        device = self._conversation_device()
        inputs = {key: value.to(device) for key, value in inputs.items()}
        torch = import_optional("torch", ["torch"])
        ctx = getattr(torch, "inference_mode", None) or torch.no_grad
        with ctx():
            output_ids = self.conversation_model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
            )
        return self.conversation_tokenizer.decode(
            output_ids[0], skip_special_tokens=True
        )

    def summarize_long_document(self, document: str) -> str:
        """Summarize arbitrarily long documents using hierarchical LED passes."""

        if not document.strip():
            return ""

        initial_summaries = self._summarize_in_chunks(document)
        if not initial_summaries:
            return ""
        if len(initial_summaries) == 1:
            return initial_summaries[0]
        return self._reduce_summaries(initial_summaries)

    def _reduce_summaries(self, summaries: List[str]) -> str:
        """Collapse intermediate summaries into a single final summary (iterative)."""

        current = [s for s in (x.strip() for x in summaries) if s]
        if not current:
            return ""
        # Avoid deep recursion by iteratively condensing until it fits.
        # Add a conservative iteration cap to prevent degenerate loops.
        for _ in range(32):
            merged_text = "\n\n".join(current)
            if not merged_text:
                return ""
            if self._count_tokens(merged_text) <= self.chunk_token_length:
                return self._summarize_chunk(merged_text)
            next_level = self._summarize_in_chunks(
                merged_text, chunk_tokens=self.chunk_token_length
            )
            if not next_level:
                return merged_text
            if len(next_level) == 1:
                return next_level[0]
            current = [s for s in (x.strip() for x in next_level) if s]
        # Fallback if iteration cap reached; return best-effort merge
        return self._summarize_chunk("\n\n".join(current))

    def _summarize_in_chunks(
        self, text: str, *, chunk_tokens: Optional[int] = None
    ) -> List[str]:
        """Summarize each chunk of the provided text."""

        summaries: List[str] = []
        for chunk in self._chunk_text(text, chunk_tokens=chunk_tokens):
            summaries.append(self._summarize_chunk(chunk))
        return summaries

    def _summarize_chunk(self, chunk_text: str) -> str:
        """Summarize a single chunk with LED."""

        torch = import_optional("torch", ["torch"])
        inputs = self.long_document_tokenizer(
            chunk_text,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_long_document_tokens,
        )
        inputs = {
            key: value.to(self.long_document_device) for key, value in inputs.items()
        }
        global_attention_mask = torch.zeros_like(inputs["input_ids"])
        global_attention_mask[:, 0] = 1
        ctx = getattr(torch, "inference_mode", None) or torch.no_grad
        with ctx():
            summary_ids = self.long_document_model.generate(
                **inputs,
                global_attention_mask=global_attention_mask,
                max_length=self.summary_max_length,
                num_beams=self.summary_num_beams,
                early_stopping=True,
            )
        return self.long_document_tokenizer.decode(
            summary_ids[0], skip_special_tokens=True
        )

    def _chunk_text(
        self, text: str, *, chunk_tokens: Optional[int] = None
    ) -> Iterable[str]:
        """Yield overlapping text chunks within the LED context window."""

        chunk_size = min(
            chunk_tokens or self.chunk_token_length, self.max_long_document_tokens
        )
        chunk_size = max(chunk_size, 128)
        overlap = min(self.chunk_overlap, chunk_size // 2)
        encoding = self.long_document_tokenizer(
            text,
            return_tensors="pt",
            truncation=False,
            add_special_tokens=False,
        )
        input_ids = encoding["input_ids"][0]
        total_tokens = input_ids.size(0)
        if total_tokens == 0:
            return
        start = 0
        while start < total_tokens:
            end = min(start + chunk_size, total_tokens)
            chunk_ids = input_ids[start:end]
            chunk_text = self.long_document_tokenizer.decode(
                chunk_ids,
                skip_special_tokens=True,
            )
            if chunk_text.strip():
                yield chunk_text
            if end >= total_tokens:
                break
            start = max(end - overlap, 0)
            if start == end:
                break

    def _count_tokens(self, text: str) -> int:
        """Count tokens using the LED tokenizer."""

        return len(
            self.long_document_tokenizer(
                text,
                add_special_tokens=False,
                return_attention_mask=False,
            )["input_ids"]
        )

    def count_long_document_tokens(self, text: str) -> int:
        """Public helper exposing token counts for downstream agents."""

        return self._count_tokens(text)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pipeline = LongContextPipeline()
    dummy_paragraph = (
        "The Export Administration Regulations (EAR) govern the export and re-export of "
        "certain goods, software, and technology. "
    )
    long_dummy_document = "\n\n".join(dummy_paragraph for _ in range(200))
    summary = pipeline.summarize_long_document(long_dummy_document)
    print("Summary:\n", summary)
