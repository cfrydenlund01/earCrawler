import pytest
import torch
from torch.utils.data import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)


class LineDataset(Dataset):
    """A simple dataset wrapping text lines."""

    def __init__(self, lines, tokenizer):
        self.lines = lines
        self.tokenizer = tokenizer

    def __len__(self):
        return len(self.lines)

    def __getitem__(self, idx):
        enc = self.tokenizer(self.lines[idx], return_tensors="pt")
        item = {k: v.squeeze(0) for k, v in enc.items()}
        item["labels"] = item["input_ids"].clone()
        return item


@pytest.mark.gpu
def test_tiny_finetune_smoke():
    """Fine-tuning tiny GPT-2 should reduce perplexity and stay under memory limits."""
    if not torch.cuda.is_available():
        pytest.skip("CUDA required")

    device = torch.device("cuda")

    model_name = "sshleifer/tiny-gpt2"
    model = AutoModelForCausalLM.from_pretrained(model_name).to(device)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.pad_token = tokenizer.eos_token

    lines = [
        "Ear training line one.",
        "Ear training line two.",
        "Ear training line three.",
        "Ear training line four.",
        "Ear training line five.",
        "Ear training line six.",
        "Ear training line seven.",
        "Ear training line eight.",
        "Ear training line nine.",
        "Ear training line ten.",
    ]
    text = "\n".join(lines)

    dataset = LineDataset(lines, tokenizer)
    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    def perplexity(m):
        m.eval()
        with torch.no_grad():
            enc = tokenizer(text, return_tensors="pt").to(device)
            loss = m(**enc, labels=enc["input_ids"]).loss
        return torch.exp(loss).item()

    initial_ppl = perplexity(model)

    training_args = TrainingArguments(
        output_dir="./tmp_tiny_finetune",
        per_device_train_batch_size=1,
        num_train_epochs=1,
        learning_rate=1e-3,
        logging_steps=10,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=data_collator,
    )

    torch.cuda.reset_peak_memory_stats()
    trainer.train()
    max_mem = torch.cuda.max_memory_allocated()

    final_ppl = perplexity(model)

    assert final_ppl <= initial_ppl * 0.95
    assert max_mem < 9 * 1024**3
