import argparse
import json
import time
from pathlib import Path

from earCrawler.utils.import_guard import import_optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run evaluation on QA items",
    )
    parser.add_argument(
        "--model-path",
        required=True,
        help="Path to the base model with adapters",
    )
    parser.add_argument(
        "--data-file",
        required=True,
        help="Path to JSONL with evaluation items",
    )
    parser.add_argument(
        "--output-file",
        required=True,
        help="Where to write the metrics JSON",
    )
    return parser.parse_args()


def load_model(model_path: str):
    transformers = import_optional("transformers", ["transformers"])
    peft = import_optional("peft", ["peft"])

    tokenizer = transformers.AutoTokenizer.from_pretrained(model_path)
    model = transformers.AutoModelForCausalLM.from_pretrained(
        model_path, device_map="auto"
    )
    try:
        model = peft.PeftModel.from_pretrained(model, model_path)
    except Exception:
        pass
    model.eval()
    return tokenizer, model


def evaluate(model, tokenizer, data):
    torch = import_optional("torch", ["torch"])
    device = next(model.parameters()).device
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    correct = 0
    latencies = []
    for item in data:
        prompt = item["question"]
        start = time.perf_counter()
        inputs = tokenizer(prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=32)
        end = time.perf_counter()
        latencies.append(end - start)
        text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        prompt_len = len(prompt)
        answer = text[prompt_len:].strip()
        if answer == item["ground_truth"]:
            correct += 1
    accuracy = correct / len(data) if data else 0.0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    if torch.cuda.is_available():
        peak_mem = torch.cuda.max_memory_allocated()
    else:
        peak_mem = 0
    return {
        "accuracy": accuracy,
        "avg_latency": avg_latency,
        "peak_gpu_memory": peak_mem,
    }


def main() -> None:
    args = parse_args()
    data_file = Path(args.data_file)
    with data_file.open("r", encoding="utf-8") as f:
        data = [json.loads(line) for line in f]
    tokenizer, model = load_model(args.model_path)
    metrics = evaluate(model, tokenizer, data)
    out_path = Path(args.output_file)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)


if __name__ == "__main__":
    main()
