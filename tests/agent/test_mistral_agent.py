"""Tests for the Mistral agent."""

from __future__ import annotations

from pathlib import Path

import importlib
import sys
import types


root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))


class DummyRetriever:
    def __init__(self) -> None:
        self.calls = []

    def query(self, query: str, k: int = 5):  # noqa: D401
        self.calls.append((query, k))
        return ["ctx1", "ctx2"]


class DummyLegalBERT:
    def filter(self, query: str, contexts):  # noqa: D401
        return contexts


class DummyTokenizer:
    def __call__(self, text: str, return_tensors=None):  # noqa: D401
        return {"input_ids": [[0, 1]]}

    def decode(self, ids, skip_special_tokens=True):  # noqa: D401
        return "answer"

    def save_pretrained(self, path):  # noqa: D401
        Path(path).mkdir(parents=True, exist_ok=True)


class DummyModel:
    def generate(self, **kwargs):  # noqa: D401
        return [[0, 1]]

    def save_pretrained(self, path):  # noqa: D401
        Path(path).mkdir(parents=True, exist_ok=True)


class DummyLongContextPipeline:
    chunk_token_length = 5

    def __init__(self) -> None:
        self.calls = []

    def count_long_document_tokens(self, text: str) -> int:
        return 10

    def summarize_long_document(self, text: str) -> str:
        self.calls.append(text)
        return f"summary:{text}"


class DummyDataset:
    def __init__(self, data):
        self.data = data

    @classmethod
    def from_dict(cls, data):
        return cls(data)

    def map(self, func):
        return self


class DummyTrainer:
    def __init__(self, model, train_dataset, args):  # noqa: D401
        self.model = model
        self.train_dataset = train_dataset
        self.args = args

    def train(self):  # noqa: D401
        pass


def _import_agent(monkeypatch):
    """Import the mistral agent with heavy deps stubbed."""
    monkeypatch.setitem(
        sys.modules,
        "bitsandbytes",
        types.SimpleNamespace(nn=types.SimpleNamespace(Linear4bit=object)),
    )
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        types.SimpleNamespace(
            AutoModelForCausalLM=object,
            AutoModelForSeq2SeqLM=object,
            AutoTokenizer=object,
            BitsAndBytesConfig=object,
            Trainer=object,
            TrainingArguments=object,
        ),
    )
    monkeypatch.setitem(sys.modules, "datasets", types.SimpleNamespace(Dataset=object))
    monkeypatch.setitem(
        sys.modules,
        "peft",
        types.SimpleNamespace(
            LoraConfig=object, get_peft_model=lambda *a, **k: object()
        ),
    )
    mistral_agent = importlib.import_module("earCrawler.agent.mistral_agent")
    importlib.reload(mistral_agent)
    return mistral_agent


def test_agent_answer_returns_string(monkeypatch) -> None:
    mistral_agent = _import_agent(monkeypatch)
    Agent = mistral_agent.Agent
    retriever = DummyRetriever()
    agent = Agent(
        retriever=retriever,
        legalbert=DummyLegalBERT(),
        model=DummyModel(),
        tokenizer=DummyTokenizer(),
    )
    assert isinstance(agent.answer("q"), str)


def test_agent_uses_long_context_pipeline(monkeypatch) -> None:
    mistral_agent = _import_agent(monkeypatch)
    captured_contexts = {}

    def fake_build(self, query, contexts):
        captured_contexts["contexts"] = contexts
        return "prompt"

    monkeypatch.setattr(mistral_agent.Agent, "_build_prompt", fake_build, raising=False)

    pipeline = DummyLongContextPipeline()
    agent = mistral_agent.Agent(
        retriever=DummyRetriever(),
        legalbert=DummyLegalBERT(),
        model=DummyModel(),
        tokenizer=DummyTokenizer(),
        long_context_pipeline=pipeline,
    )

    agent.answer("q")
    assert pipeline.calls == ["ctx1", "ctx2"]
    assert captured_contexts["contexts"] == ["summary:ctx1", "summary:ctx2"]


def test_train_qlora_adapter_runs(tmp_path, monkeypatch) -> None:
    mistral_agent = _import_agent(monkeypatch)

    def fake_loader(*_a, **_k):
        return DummyTokenizer(), DummyModel()

    monkeypatch.setattr(mistral_agent, "Dataset", DummyDataset)

    class DummyTrainingArgs:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(mistral_agent, "TrainingArguments", DummyTrainingArgs)
    monkeypatch.setattr(mistral_agent, "load_mistral_with_lora", fake_loader)
    out_dir = tmp_path / Path("models\\mistral7b\\qlora_adapter")
    mistral_agent.train_qlora_adapter(
        model_name="hf-internal-testing/tiny-random-gpt2",
        output_dir=out_dir,
        use_4bit=False,
        trainer_cls=DummyTrainer,
    )
    assert out_dir.exists()
