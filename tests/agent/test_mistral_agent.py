"""Tests for the Mistral agent."""

from __future__ import annotations

from pathlib import Path

import sys
import types
sys.modules.setdefault("bitsandbytes", types.SimpleNamespace(nn=types.SimpleNamespace(Linear4bit=object)))
sys.modules.setdefault("transformers", types.SimpleNamespace(AutoModelForCausalLM=object, AutoTokenizer=object, BitsAndBytesConfig=object, Trainer=object, TrainingArguments=object))
sys.modules.setdefault("datasets", types.SimpleNamespace(Dataset=object))
sys.modules.setdefault("peft", types.SimpleNamespace(LoraConfig=object, get_peft_model=lambda *a, **k: object()))
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))



from earCrawler.agent import mistral_agent
from earCrawler.agent.mistral_agent import Agent


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


def test_agent_answer_returns_string() -> None:
    retriever = DummyRetriever()
    agent = Agent(
        retriever=retriever,
        legalbert=DummyLegalBERT(),
        model=DummyModel(),
        tokenizer=DummyTokenizer(),
    )
    assert isinstance(agent.answer("q"), str)


def test_train_qlora_adapter_runs(tmp_path, monkeypatch) -> None:
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
