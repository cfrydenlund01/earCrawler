import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from earCrawler.utils import import_guard

LABEL_PATTERNS = [
    (
        "prohibited",
        [
            "is prohibited",
            "are prohibited",
            "not permitted",
            "cannot export",
            "ban",
            "prohibited export",
        ],
    ),
    (
        "license_required",
        [
            "license is required",
            "requires a license",
            "must obtain a license",
            "license needed",
            "license before exporting",
        ],
    ),
    (
        "permitted_with_license",
        [
            "permitted with a license",
            "allowed with a license",
            "allowed under license",
            "license exception tmp",
            "export can proceed once a license",
        ],
    ),
    (
        "no_license_required",
        [
            "no license is required",
            "does not require a license",
            "without a license to a country group b destination",
        ],
    ),
    (
        "permitted",
        [
            "can export",
            "is permitted",
            "allowed to export",
            "export can proceed",
            "authorized to export",
        ],
    ),
    (
        "unanswerable",
        [
            "cannot be answered",
            "not enough information",
            "insufficient information",
            "outside the covered export regulations",
            "decline to answer",
            "no basis to answer",
        ],
    ),
]


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
    transformers = import_guard.import_optional("transformers", ["transformers"])
    peft = import_guard.import_optional("peft", ["peft"])

    tokenizer = transformers.AutoTokenizer.from_pretrained(model_path)
    model = transformers.AutoModelForCausalLM.from_pretrained(
        model_path, device_map="auto"
    )
    try:
        model = peft.PeftModel.from_pretrained(model, model_path)
    except Exception:
        # Adapters are optional; fall back to the base model if loading fails.
        pass
    model.eval()
    return tokenizer, model


def _infer_label(answer: str) -> str:
    normalized = answer.strip().lower()
    if not normalized:
        return "unanswerable"
    for label, patterns in LABEL_PATTERNS:
        if any(pattern in normalized for pattern in patterns):
            return label
    return "unknown"


def evaluate(model, tokenizer, data: List[Dict[str, Any]]):
    torch = import_guard.import_optional("torch", ["torch"])
    device = next(model.parameters()).device
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    correct = 0
    label_correct = 0
    label_total = 0
    unanswerable_correct = 0
    unanswerable_total = 0
    latencies = []
    by_task: Dict[str, Dict[str, float]] = {}
    for item in data:
        prompt = item.get("question", "")
        ground_truth = item.get("ground_truth", {}) or {}
        gt_answer = (ground_truth.get("answer_text") or "").strip()
        gt_label = (ground_truth.get("label") or "").strip().lower()
        start = time.perf_counter()
        inputs = tokenizer(prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=32)
        end = time.perf_counter()
        latencies.append(end - start)
        text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        prompt_len = len(prompt)
        answer = text[prompt_len:].strip()
        if answer == gt_answer:
            correct += 1
        pred_label = _infer_label(answer)
        if gt_label:
            label_total += 1
            if pred_label == gt_label:
                label_correct += 1
        if gt_label == "unanswerable":
            unanswerable_total += 1
            if pred_label == "unanswerable":
                unanswerable_correct += 1

        task = str(item.get("task", "") or "").strip()
        if task:
            stats = by_task.setdefault(
                task,
                {
                    "count": 0.0,
                    "answer_correct": 0.0,
                    "label_total": 0.0,
                    "label_correct": 0.0,
                },
            )
            stats["count"] += 1
            if answer == gt_answer:
                stats["answer_correct"] += 1
            if gt_label:
                stats["label_total"] += 1
                if pred_label == gt_label:
                    stats["label_correct"] += 1
    accuracy = correct / len(data) if data else 0.0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    if torch.cuda.is_available():
        peak_mem = torch.cuda.max_memory_allocated()
    else:
        peak_mem = 0
    label_accuracy = label_correct / label_total if label_total else 0.0
    unanswerable_accuracy = (
        unanswerable_correct / unanswerable_total if unanswerable_total else 0.0
    )
    task_breakdown: Dict[str, Dict[str, float]] = {}
    for task, stats in by_task.items():
        count = stats["count"] or 1.0
        task_breakdown[task] = {
            "count": int(stats["count"]),
            "accuracy": stats["answer_correct"] / count,
            "label_accuracy": (
                stats["label_correct"] / stats["label_total"]
                if stats["label_total"]
                else 0.0
            ),
        }
    return {
        "accuracy": accuracy,
        "avg_latency": avg_latency,
        "peak_gpu_memory": peak_mem,
        "label_accuracy": label_accuracy,
        "unanswerable_accuracy": unanswerable_accuracy,
        "by_task": task_breakdown,
    }


def main() -> None:
    args = parse_args()
    data_file = Path(args.data_file)
    with data_file.open("r", encoding="utf-8") as f:
        data = [json.loads(line) for line in f if line.strip()]
    tokenizer, model = load_model(args.model_path)
    metrics = evaluate(model, tokenizer, data)

    # Include minimal run metadata alongside core metrics for research logging.
    result = {
        **metrics,
        "model_path": args.model_path,
        "data_file": str(data_file),
        "num_items": len(data),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    out_path = Path(args.output_file)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
