from __future__ import annotations

"""
Phase 5.3 training runner for the first production-oriented 7B fine-tuning pass.

This script is intentionally opt-in and writes all outputs under `dist/training/`.
It does not change the supported runtime surface by itself.
"""

import argparse
import hashlib
import inspect
import json
import gc
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_MODEL = "google/gemma-4-E4B-it"
DEFAULT_SYSTEM_PROMPT = (
    "Answer only from cited EAR evidence. "
    "If evidence is insufficient, refuse and explain what is missing."
)


@dataclass(frozen=True)
class SnapshotMetadata:
    snapshot_id: str
    snapshot_sha256: str
    snapshot_manifest_path: str | None


@dataclass(frozen=True)
class SnapshotContract:
    expected_manifest_path: Path | None
    expected_payload_path: Path | None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_slug(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "unknown"


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count_jsonl_records(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Retrieval corpus contains invalid JSON at line {line_no}: {path}"
                ) from exc
            count += 1
    return count


def _resolve_repo_relative(path_value: str) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path.resolve()
    return (REPO_ROOT / path).resolve()


def _contains_placeholder(value: str | None) -> bool:
    token = str(value or "").strip()
    return "<" in token and ">" in token


def _load_snapshot_contract(training_input_contract_path: Path) -> SnapshotContract:
    contract = _load_json(training_input_contract_path)
    authoritative = contract.get("authoritative_sources")
    if not isinstance(authoritative, dict):
        raise ValueError("Training input contract is missing authoritative_sources.")

    manifest_raw = str(authoritative.get("offline_snapshot_manifest") or "").strip()
    payload_raw = str(authoritative.get("offline_snapshot_payload") or "").strip()
    if manifest_raw and _contains_placeholder(manifest_raw):
        raise ValueError(
            "Training input contract contains a placeholder offline_snapshot_manifest."
        )
    if payload_raw and _contains_placeholder(payload_raw):
        raise ValueError(
            "Training input contract contains a placeholder offline_snapshot_payload."
        )

    manifest_path = _resolve_repo_relative(manifest_raw) if manifest_raw else None
    payload_path = _resolve_repo_relative(payload_raw) if payload_raw else None
    return SnapshotContract(
        expected_manifest_path=manifest_path,
        expected_payload_path=payload_path,
    )


def _validate_training_corpus_preflight(
    *,
    retrieval_corpus_path: Path,
    training_input_contract_path: Path,
    index_meta_path: Path,
) -> tuple[str, int]:
    if not training_input_contract_path.exists():
        raise FileNotFoundError(
            f"Training input contract not found: {training_input_contract_path}"
        )
    if not index_meta_path.exists():
        raise FileNotFoundError(f"FAISS index metadata not found: {index_meta_path}")

    contract = _load_json(training_input_contract_path)
    authoritative = contract.get("authoritative_sources")
    if not isinstance(authoritative, dict):
        raise ValueError(
            "Training input contract is missing authoritative_sources."
        )
    expected_corpus_raw = str(
        authoritative.get("retrieval_corpus_jsonl") or ""
    ).strip()
    if not expected_corpus_raw:
        raise ValueError(
            "Training input contract is missing authoritative_sources.retrieval_corpus_jsonl."
        )
    expected_corpus_path = _resolve_repo_relative(expected_corpus_raw)
    if retrieval_corpus_path != expected_corpus_path:
        raise ValueError(
            "Configured retrieval corpus path does not match training input contract. "
            f"configured='{retrieval_corpus_path}' expected='{expected_corpus_path}'"
        )
    expected_index_meta_raw = str(authoritative.get("faiss_index_meta_json") or "").strip()
    if expected_index_meta_raw:
        expected_index_meta_path = _resolve_repo_relative(expected_index_meta_raw)
        if index_meta_path != expected_index_meta_path:
            raise ValueError(
                "Configured FAISS index metadata path does not match training input contract. "
                f"configured='{index_meta_path}' expected='{expected_index_meta_path}'"
            )

    index_meta = _load_json(index_meta_path)
    expected_digest = str(index_meta.get("corpus_digest") or "").strip()
    if not expected_digest:
        raise ValueError(
            "FAISS index metadata is missing corpus_digest."
        )
    if "doc_count" not in index_meta:
        raise ValueError("FAISS index metadata is missing doc_count.")
    expected_doc_count = int(index_meta["doc_count"])

    actual_digest = _sha256_file(retrieval_corpus_path)
    actual_doc_count = _count_jsonl_records(retrieval_corpus_path)
    if actual_digest != expected_digest:
        raise ValueError(
            "Retrieval corpus digest mismatch vs FAISS metadata. "
            f"corpus='{actual_digest}' index_meta='{expected_digest}'"
        )
    if actual_doc_count != expected_doc_count:
        raise ValueError(
            "Retrieval corpus document count mismatch vs FAISS metadata. "
            f"corpus={actual_doc_count} index_meta={expected_doc_count}"
        )
    return actual_digest, actual_doc_count


def _validate_snapshot_preflight(
    *,
    snapshot: SnapshotMetadata,
    snapshot_manifest: Path | None,
    training_input_contract_path: Path,
    index_meta_path: Path,
) -> None:
    contract = _load_snapshot_contract(training_input_contract_path)
    if contract.expected_manifest_path is None:
        if snapshot.snapshot_id in {"", "unknown-snapshot"} or _contains_placeholder(
            snapshot.snapshot_id
        ):
            raise ValueError(
                "Snapshot ID is required and cannot be unknown/placeholder."
            )
        if snapshot.snapshot_sha256 in {"", "unknown"} or _contains_placeholder(
            snapshot.snapshot_sha256
        ):
            raise ValueError(
                "Snapshot SHA-256 is required and cannot be unknown/placeholder."
            )
        return

    if snapshot_manifest is None:
        raise ValueError(
            "Configured snapshot manifest is required by training input contract."
        )
    if snapshot_manifest != contract.expected_manifest_path:
        raise ValueError(
            "Configured snapshot manifest path does not match training input contract. "
            f"configured='{snapshot_manifest}' expected='{contract.expected_manifest_path}'"
        )
    if not snapshot_manifest.exists():
        raise FileNotFoundError(f"Snapshot manifest not found: {snapshot_manifest}")

    manifest = _load_json(snapshot_manifest)
    manifest_snapshot_id = str(manifest.get("snapshot_id") or "").strip()
    payload = manifest.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Snapshot manifest is missing payload metadata.")
    manifest_snapshot_sha = str(payload.get("sha256") or "").strip().lower()
    payload_relative = str(payload.get("path") or "").strip()

    if not manifest_snapshot_id:
        raise ValueError("Snapshot manifest is missing snapshot_id.")
    if _contains_placeholder(manifest_snapshot_id):
        raise ValueError("Snapshot manifest snapshot_id cannot be a placeholder.")
    if not re.fullmatch(r"[0-9a-f]{64}", manifest_snapshot_sha):
        raise ValueError("Snapshot manifest payload.sha256 must be a valid SHA-256 hex.")

    if contract.expected_payload_path is not None:
        expected_payload = contract.expected_payload_path
        if payload_relative:
            manifest_payload = (snapshot_manifest.parent / payload_relative).resolve()
        else:
            manifest_payload = None
        if manifest_payload is None or manifest_payload != expected_payload:
            raise ValueError(
                "Snapshot payload path in manifest does not match training input contract. "
                f"manifest='{manifest_payload}' expected='{expected_payload}'"
            )

    if snapshot.snapshot_id != manifest_snapshot_id:
        raise ValueError(
            "Configured snapshot_id does not match snapshot manifest. "
            f"configured='{snapshot.snapshot_id}' manifest='{manifest_snapshot_id}'"
        )
    if snapshot.snapshot_sha256.lower() != manifest_snapshot_sha:
        raise ValueError(
            "Configured snapshot_sha256 does not match snapshot manifest payload hash. "
            f"configured='{snapshot.snapshot_sha256}' manifest='{manifest_snapshot_sha}'"
        )

    index_meta = _load_json(index_meta_path)
    index_snapshot = index_meta.get("snapshot")
    if isinstance(index_snapshot, dict):
        index_snapshot_id = str(index_snapshot.get("snapshot_id") or "").strip()
        index_snapshot_sha = str(index_snapshot.get("snapshot_sha256") or "").strip().lower()
        if index_snapshot_id and index_snapshot_id != manifest_snapshot_id:
            raise ValueError(
                "FAISS index metadata snapshot_id does not match snapshot manifest. "
                f"index_meta='{index_snapshot_id}' manifest='{manifest_snapshot_id}'"
            )
        if index_snapshot_sha and index_snapshot_sha != manifest_snapshot_sha:
            raise ValueError(
                "FAISS index metadata snapshot_sha256 does not match snapshot manifest. "
                f"index_meta='{index_snapshot_sha}' manifest='{manifest_snapshot_sha}'"
            )


def _validate_configured_snapshot_fields(
    *,
    snapshot_manifest_value: Any,
    snapshot_id_value: Any,
    snapshot_sha256_value: Any,
) -> None:
    snapshot_manifest_raw = str(snapshot_manifest_value or "").strip()
    snapshot_id_raw = str(snapshot_id_value or "").strip()
    snapshot_sha256_raw = str(snapshot_sha256_value or "").strip()

    if snapshot_manifest_raw and _contains_placeholder(snapshot_manifest_raw):
        raise ValueError(
            "Configured snapshot_manifest cannot contain placeholder tokens."
        )
    if snapshot_id_raw and _contains_placeholder(snapshot_id_raw):
        raise ValueError("Configured snapshot_id cannot contain placeholder tokens.")
    if snapshot_sha256_raw and _contains_placeholder(snapshot_sha256_raw):
        raise ValueError(
            "Configured snapshot_sha256 cannot contain placeholder tokens."
        )


def _validate_qlora_preflight(
    *,
    require_qlora_4bit: bool,
    use_4bit: bool,
    base_model: str,
) -> None:
    if require_qlora_4bit and not use_4bit:
        raise ValueError(
            "QLoRA 4-bit evidence is required for this run, but use_4bit is false. "
            f"Enable --use-4bit for base model '{base_model}'."
        )


def _validate_qlora_runtime_preflight(
    *,
    require_qlora_4bit: bool,
    use_4bit: bool,
    base_model: str,
) -> None:
    if not (require_qlora_4bit or use_4bit):
        return

    try:
        import torch
    except Exception as exc:  # pragma: no cover - environment specific import failure
        raise ValueError(
            "QLoRA runtime preflight failed: PyTorch is not importable in this environment."
        ) from exc

    cuda_available = bool(torch.cuda.is_available())
    cuda_device_count = int(torch.cuda.device_count()) if cuda_available else 0
    torch_version = str(getattr(torch, "__version__", "unknown"))
    if "+cpu" in torch_version.lower() or not cuda_available or cuda_device_count < 1:
        raise ValueError(
            "QLoRA runtime preflight failed: CUDA-capable PyTorch is required for the "
            f"7B QLoRA candidate path on '{base_model}'. "
            f"Detected torch='{torch_version}', cuda_available={cuda_available}, "
            f"cuda_device_count={cuda_device_count}. "
            "Install a CUDA-enabled torch build on a host with at least one visible CUDA device."
        )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _short_text(value: str, max_chars: int = 280) -> str:
    text = _normalize_space(value)
    if len(text) <= max_chars:
        return text
    clipped = text[: max_chars - 3].rstrip()
    return f"{clipped}..."


def _model_slug(base_model: str) -> str:
    slug = _safe_slug(base_model.split("/")[-1]).replace(".", "")
    slug = slug.replace("instruct", "").strip("-")
    return slug or "model"


def _extract_snapshot_metadata(
    *,
    snapshot_manifest: Path | None,
    snapshot_id: str | None,
    snapshot_sha256: str | None,
) -> SnapshotMetadata:
    resolved_id = (snapshot_id or "").strip()
    resolved_sha = (snapshot_sha256 or "").strip()
    manifest_path: str | None = None
    if snapshot_manifest and snapshot_manifest.exists():
        manifest = _load_json(snapshot_manifest)
        resolved_id = str(manifest.get("snapshot_id") or resolved_id).strip()
        payload = manifest.get("payload")
        if isinstance(payload, dict):
            resolved_sha = str(payload.get("sha256") or resolved_sha).strip()
        manifest_path = str(snapshot_manifest)

    return SnapshotMetadata(
        snapshot_id=resolved_id or "unknown-snapshot",
        snapshot_sha256=resolved_sha or "unknown",
        snapshot_manifest_path=manifest_path,
    )


def _resolve_run_id(
    *,
    run_id: str | None,
    base_model: str,
    snapshot_id: str,
    package_version: int,
) -> str:
    if run_id:
        return _safe_slug(run_id)
    date_tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (
        f"{_model_slug(base_model)}-ear-{date_tag}-"
        f"snapshot-{_safe_slug(snapshot_id)}-v{package_version}"
    )


def _read_retrieval_records(path: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            section_id = _normalize_space(
                str(payload.get("section_id") or payload.get("id") or "")
            )
            doc_id = _normalize_space(str(payload.get("doc_id") or section_id))
            source_ref = _normalize_space(str(payload.get("source_ref") or "unknown"))
            text = _normalize_space(str(payload.get("text") or ""))
            if not section_id or not text:
                continue
            records.append(
                {
                    "section_id": section_id,
                    "doc_id": doc_id or section_id,
                    "source_ref": source_ref,
                    "text": text,
                    "line_no": str(line_no),
                }
            )
    records.sort(key=lambda item: (item["section_id"], item["doc_id"], item["line_no"]))
    return records


def _answer_example(
    *,
    record: dict[str, str],
    idx: int,
    base_model: str,
    snapshot: SnapshotMetadata,
    corpus_digest: str,
) -> dict[str, Any]:
    section_id = record["section_id"]
    quote = _short_text(record["text"], 260)
    answer_text = _short_text(
        f"{quote} See {section_id} for the authoritative EAR text.", 300
    )
    question = f"What does {section_id} say in the EAR?"
    example_id = f"ear-answer-{_safe_slug(section_id)}-{idx:05d}"
    return {
        "schema_version": "instruction-tuning.v1",
        "example_id": example_id,
        "split": "train",
        "task": "answer",
        "base_model": base_model,
        "question": question,
        "messages": [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer_text},
        ],
        "evidence": [
            {
                "doc_id": record["doc_id"],
                "section_id": section_id,
                "source_ref": record["source_ref"],
                "quote": quote,
            }
        ],
        "target": {
            "answer": answer_text,
            "citations": [section_id],
            "refusal": False,
        },
        "provenance": {
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_sha256": snapshot.snapshot_sha256,
            "retrieval_corpus_digest": corpus_digest,
        },
    }


def _refusal_example(
    *,
    record: dict[str, str],
    idx: int,
    base_model: str,
    snapshot: SnapshotMetadata,
    corpus_digest: str,
) -> dict[str, Any]:
    section_id = record["section_id"]
    question = (
        "From this evidence alone, can you determine a full export decision for "
        "an unspecified item, destination, and end-use?"
    )
    answer = (
        "I cannot determine that from the provided evidence. Please provide item "
        "classification, destination, end-use, and parties for a grounded answer."
    )
    example_id = f"ear-refusal-{_safe_slug(section_id)}-{idx:05d}"
    return {
        "schema_version": "instruction-tuning.v1",
        "example_id": example_id,
        "split": "train",
        "task": "refusal",
        "base_model": base_model,
        "question": question,
        "messages": [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ],
        "evidence": [
            {
                "doc_id": record["doc_id"],
                "section_id": section_id,
                "source_ref": record["source_ref"],
                "quote": _short_text(record["text"], 220),
            }
        ],
        "target": {
            "answer": answer,
            "citations": [],
            "refusal": True,
        },
        "provenance": {
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_sha256": snapshot.snapshot_sha256,
            "retrieval_corpus_digest": corpus_digest,
        },
    }


def _build_examples(
    *,
    records: list[dict[str, str]],
    base_model: str,
    snapshot: SnapshotMetadata,
    corpus_digest: str,
    max_examples: int,
    refusal_every: int,
) -> list[dict[str, Any]]:
    if max_examples <= 0:
        raise ValueError("--max-examples must be > 0")
    if refusal_every <= 0:
        raise ValueError("--refusal-every must be > 0")
    if not records:
        raise ValueError("No usable retrieval corpus records were found.")

    examples: list[dict[str, Any]] = []
    idx = 1
    rec_idx = 0
    while len(examples) < max_examples:
        record = records[rec_idx % len(records)]
        examples.append(
            _answer_example(
                record=record,
                idx=idx,
                base_model=base_model,
                snapshot=snapshot,
                corpus_digest=corpus_digest,
            )
        )
        idx += 1
        if len(examples) >= max_examples:
            break
        if idx % refusal_every == 0:
            examples.append(
                _refusal_example(
                    record=record,
                    idx=idx,
                    base_model=base_model,
                    snapshot=snapshot,
                    corpus_digest=corpus_digest,
                )
            )
            idx += 1
        rec_idx += 1

    examples = examples[:max_examples]
    examples.sort(key=lambda item: str(item.get("example_id") or ""))
    return examples


def _write_examples_jsonl(path: Path, examples: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for example in examples:
            handle.write(json.dumps(example, ensure_ascii=True, sort_keys=True) + "\n")


def _format_sft_text(example: dict[str, Any]) -> str:
    messages = example.get("messages") or []
    segments: list[str] = []
    for msg in messages:
        role = str(msg.get("role") or "").strip().lower()
        content = _normalize_space(str(msg.get("content") or ""))
        if not role or not content:
            continue
        segments.append(f"<|{role}|>\n{content}")
    return "\n\n".join(segments) + "\n"


def _git_head() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    value = (proc.stdout or "").strip()
    return value or None


def _load_training_deps() -> tuple[Any, Any, Any, Any, Any, Any, Any]:
    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    return (
        torch,
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
        (LoraConfig, get_peft_model, prepare_model_for_kbit_training),
    )


def _collect_quantization_evidence(model: Any) -> dict[str, Any]:
    quantization_config = getattr(model, "quantization_config", None)
    config_load_in_4bit: bool | None = None
    quantization_type: str | None = None
    compute_dtype: str | None = None
    use_double_quant: bool | None = None
    if quantization_config is not None:
        config_load_in_4bit = bool(getattr(quantization_config, "load_in_4bit", False))
        raw_type = getattr(quantization_config, "bnb_4bit_quant_type", None)
        quantization_type = str(raw_type) if raw_type is not None else None
        raw_dtype = getattr(quantization_config, "bnb_4bit_compute_dtype", None)
        compute_dtype = str(raw_dtype) if raw_dtype is not None else None
        raw_double_quant = getattr(quantization_config, "bnb_4bit_use_double_quant", None)
        if raw_double_quant is not None:
            use_double_quant = bool(raw_double_quant)
    model_flag_is_loaded_in_4bit = bool(getattr(model, "is_loaded_in_4bit", False))
    effective_use_4bit = bool(model_flag_is_loaded_in_4bit or config_load_in_4bit)
    return {
        "effective_use_4bit": effective_use_4bit,
        "model_flag_is_loaded_in_4bit": model_flag_is_loaded_in_4bit,
        "quantization_config_load_in_4bit": config_load_in_4bit,
        "quantization_config_type": quantization_type,
        "quantization_config_compute_dtype": compute_dtype,
        "quantization_config_double_quant": use_double_quant,
    }


def _train_adapter(
    *,
    base_model: str,
    examples: list[dict[str, Any]],
    output_dir: Path,
    max_seq_len: int,
    epochs: float,
    learning_rate: float,
    batch_size: int,
    grad_accum: int,
    lora_r: int,
    lora_alpha: int,
    lora_dropout: float,
    lora_target_modules: list[str],
    use_4bit: bool,
    require_qlora_4bit: bool,
    allow_pt_bin: bool,
) -> dict[str, Any]:
    (
        torch,
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
        peft_fns,
    ) = _load_training_deps()
    LoraConfig, get_peft_model, prepare_model_for_kbit_training = peft_fns

    texts = [_format_sft_text(example) for example in examples]
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token or tokenizer.unk_token

    encodings = tokenizer(
        texts,
        truncation=True,
        padding="max_length",
        max_length=max_seq_len,
        return_tensors="pt",
    )

    class _TokenDataset:
        def __len__(self) -> int:
            return int(encodings["input_ids"].shape[0])

        def __getitem__(self, i: int) -> dict[str, Any]:
            item = {
                "input_ids": encodings["input_ids"][i],
                "attention_mask": encodings["attention_mask"][i],
            }
            item["labels"] = item["input_ids"].clone()
            return item

    model_kwargs: dict[str, Any] = {
        "trust_remote_code": True,
        "use_safetensors": not allow_pt_bin,
    }
    if torch.cuda.is_available():
        model_kwargs["device_map"] = None
        if torch.cuda.is_bf16_supported():
            model_kwargs["torch_dtype"] = torch.bfloat16
        else:
            model_kwargs["torch_dtype"] = torch.float16

    if use_4bit:
        try:
            from transformers import BitsAndBytesConfig
        except (
            Exception
        ) as exc:  # pragma: no cover - import failure is environment specific
            raise RuntimeError(
                "Requested --use-4bit but bitsandbytes support is unavailable."
            ) from exc
        compute_dtype = (
            torch.bfloat16
            if torch.cuda.is_available() and torch.cuda.is_bf16_supported()
            else torch.float16
        )
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            llm_int8_enable_fp32_cpu_offload=False,
        )

    model = AutoModelForCausalLM.from_pretrained(base_model, **model_kwargs)
    quantization_evidence = _collect_quantization_evidence(model)
    if use_4bit and not bool(quantization_evidence.get("effective_use_4bit")):
        raise RuntimeError(
            "Requested --use-4bit, but model load did not report effective 4-bit quantization."
        )
    # LoRA in peft does not recognize Gemma4ClippableLinear wrappers; when
    # clipping is disabled (default), unwrap to the inner linear so adapters can
    # be attached.
    try:
        from transformers.models.gemma4.modeling_gemma4 import Gemma4ClippableLinear
    except Exception:  # pragma: no cover - optional import
        Gemma4ClippableLinear = None

    def _unwrap_clippable_linears(mod: torch.nn.Module) -> None:
        for child_name, child in list(mod.named_children()):
            if Gemma4ClippableLinear and isinstance(child, Gemma4ClippableLinear):
                setattr(mod, child_name, child.linear)
                child = getattr(mod, child_name)
            _unwrap_clippable_linears(child)

    _unwrap_clippable_linears(model)
    if use_4bit:
        model = prepare_model_for_kbit_training(model)

    lora_cfg = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        target_modules=lora_target_modules,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_cfg)

    checkpoints_dir = output_dir / "checkpoints"
    train_args_kwargs: dict[str, Any] = {
        "output_dir": str(checkpoints_dir),
        "num_train_epochs": float(epochs),
        "learning_rate": float(learning_rate),
        "per_device_train_batch_size": int(batch_size),
        "gradient_accumulation_steps": int(grad_accum),
        "logging_steps": 1,
        "save_strategy": "epoch",
        "report_to": [],
        "remove_unused_columns": False,
        "dataloader_num_workers": 0,
        "fp16": bool(torch.cuda.is_available() and not torch.cuda.is_bf16_supported()),
        "bf16": bool(torch.cuda.is_available() and torch.cuda.is_bf16_supported()),
    }
    training_args_params = inspect.signature(TrainingArguments.__init__).parameters
    if "evaluation_strategy" in training_args_params:
        train_args_kwargs["evaluation_strategy"] = "no"
    elif "eval_strategy" in training_args_params:
        train_args_kwargs["eval_strategy"] = "no"

    train_args = TrainingArguments(**train_args_kwargs)

    trainer = Trainer(
        model=model,
        args=train_args,
        train_dataset=_TokenDataset(),
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )
    train_result = trainer.train()
    trainer.save_state()

    adapter_dir = output_dir / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)

    metrics = dict(train_result.metrics or {})
    metrics["global_step"] = int(getattr(trainer.state, "global_step", 0) or 0)
    metrics["train_samples"] = len(examples)
    metrics["adapter_dir"] = str(adapter_dir)
    metrics["qlora"] = {
        "required": bool(require_qlora_4bit),
        "requested_use_4bit": bool(use_4bit),
        **quantization_evidence,
    }
    return metrics


def _run_inference_smoke(
    *,
    base_model: str,
    adapter_dir: Path,
    prompt: str,
    max_new_tokens: int,
    use_4bit: bool,
    allow_pt_bin: bool,
) -> dict[str, Any]:
    (
        torch,
        AutoModelForCausalLM,
        AutoTokenizer,
        _,
        _trainer_cls,
        _args_cls,
        _peft_fns,
    ) = _load_training_deps()

    from peft import PeftModel

    tokenizer = AutoTokenizer.from_pretrained(str(adapter_dir), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token or tokenizer.unk_token

    model_kwargs: dict[str, Any] = {
        "trust_remote_code": True,
        "use_safetensors": not allow_pt_bin,
    }
    if torch.cuda.is_available():
        model_kwargs["device_map"] = None
        if torch.cuda.is_bf16_supported():
            model_kwargs["torch_dtype"] = torch.bfloat16
        else:
            model_kwargs["torch_dtype"] = torch.float16
    if use_4bit:
        try:
            from transformers import BitsAndBytesConfig
        except (
            Exception
        ) as exc:  # pragma: no cover - import failure is environment specific
            raise RuntimeError(
                "Smoke inference requested 4-bit load, but bitsandbytes support is unavailable."
            ) from exc
        compute_dtype = (
            torch.bfloat16
            if torch.cuda.is_available() and torch.cuda.is_bf16_supported()
            else torch.float16
        )
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            llm_int8_enable_fp32_cpu_offload=True,
        )
    model = AutoModelForCausalLM.from_pretrained(base_model, **model_kwargs)
    try:
        from transformers.models.gemma4.modeling_gemma4 import Gemma4ClippableLinear
    except Exception:  # pragma: no cover - optional import
        Gemma4ClippableLinear = None

    def _unwrap_clippable_linears(mod: torch.nn.Module) -> None:
        for child_name, child in list(mod.named_children()):
            if Gemma4ClippableLinear and isinstance(child, Gemma4ClippableLinear):
                setattr(mod, child_name, child.linear)
                child = getattr(mod, child_name)
            _unwrap_clippable_linears(child)

    _unwrap_clippable_linears(model)
    model = PeftModel.from_pretrained(model, str(adapter_dir))
    model.eval()

    encoded = tokenizer(prompt, return_tensors="pt")
    device = model.device
    encoded = {key: value.to(device) for key, value in encoded.items()}
    with torch.no_grad():
        generated = model.generate(
            **encoded,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    decoded = tokenizer.decode(generated[0], skip_special_tokens=True)
    completion = (
        decoded[len(prompt) :].strip()
        if decoded.startswith(prompt)
        else decoded.strip()
    )
    passed = bool(completion)
    return {
        "base_model": base_model,
        "adapter_dir": str(adapter_dir),
        "prompt": prompt,
        "generated_text": decoded,
        "completion": completion,
        "pass": passed,
    }


def _release_torch_memory() -> None:
    gc.collect()
    try:
        torch, *_ = _load_training_deps()
    except Exception:  # pragma: no cover - runtime environment specific
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _apply_config_file(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> argparse.Namespace:
    config_path = Path(args.config).resolve() if args.config else None
    if not config_path:
        return args
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    payload = _load_json(config_path)
    defaults: dict[str, Any] = {}
    for action in parser._actions:
        if not action.dest or action.dest == "help":
            continue
        defaults[action.dest] = action.default
    for key, value in payload.items():
        if not hasattr(args, key):
            continue
        if getattr(args, key) == defaults.get(key):
            setattr(args, key, value)
    return args


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Phase 5.3 first-pass fine-tuning and metadata capture."
    )
    parser.add_argument("--config", default=None, help="Optional JSON config path.")
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    parser.add_argument("--snapshot-manifest", type=Path, default=None)
    parser.add_argument("--snapshot-id", default=None)
    parser.add_argument("--snapshot-sha256", default=None)
    parser.add_argument(
        "--retrieval-corpus",
        type=Path,
        default=Path("data") / "faiss" / "retrieval_corpus.jsonl",
    )
    parser.add_argument(
        "--training-input-contract",
        type=Path,
        default=Path("config") / "training_input_contract.example.json",
    )
    parser.add_argument(
        "--index-meta",
        type=Path,
        default=Path("data") / "faiss" / "index.meta.json",
    )
    parser.add_argument("--output-root", type=Path, default=Path("dist") / "training")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--package-version", type=int, default=1)
    parser.add_argument("--max-examples", type=int, default=256)
    parser.add_argument("--refusal-every", type=int, default=4)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--max-seq-len", type=int, default=1024)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument(
        "--lora-target-modules",
        default="q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj",
    )
    parser.add_argument("--use-4bit", action="store_true")
    parser.add_argument(
        "--require-qlora-4bit",
        action="store_true",
        help=(
            "Require 4-bit QLoRA evidence for this run. "
            "When enabled, preflight fails unless --use-4bit is true."
        ),
    )
    parser.add_argument(
        "--allow-pt-bin",
        action="store_true",
        help=(
            "Allow loading legacy *.bin model weights. Default requires safetensors "
            "for safer loading behavior."
        ),
    )
    parser.add_argument(
        "--smoke-prompt",
        default="When is a license required under EAR section 736.2(b)?",
    )
    parser.add_argument("--smoke-max-new-tokens", type=int, default=96)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    args = _apply_config_file(args, parser)

    start_utc = _utc_now_iso()
    retrieval_corpus_path = Path(args.retrieval_corpus).resolve()
    if not retrieval_corpus_path.exists():
        print(
            f"Training corpus preflight failed: Retrieval corpus not found: {retrieval_corpus_path}",
            file=sys.stderr,
        )
        return 2
    training_input_contract_path = Path(args.training_input_contract).resolve()
    index_meta_path = Path(args.index_meta).resolve()
    try:
        corpus_digest, corpus_doc_count = _validate_training_corpus_preflight(
            retrieval_corpus_path=retrieval_corpus_path,
            training_input_contract_path=training_input_contract_path,
            index_meta_path=index_meta_path,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Training corpus preflight failed: {exc}", file=sys.stderr)
        return 2

    try:
        _validate_configured_snapshot_fields(
            snapshot_manifest_value=args.snapshot_manifest,
            snapshot_id_value=args.snapshot_id,
            snapshot_sha256_value=args.snapshot_sha256,
        )
    except ValueError as exc:
        print(f"Training snapshot preflight failed: {exc}", file=sys.stderr)
        return 2

    snapshot_manifest = (
        Path(args.snapshot_manifest).resolve() if args.snapshot_manifest else None
    )
    snapshot = _extract_snapshot_metadata(
        snapshot_manifest=snapshot_manifest,
        snapshot_id=args.snapshot_id,
        snapshot_sha256=args.snapshot_sha256,
    )
    try:
        _validate_snapshot_preflight(
            snapshot=snapshot,
            snapshot_manifest=snapshot_manifest,
            training_input_contract_path=training_input_contract_path,
            index_meta_path=index_meta_path,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Training snapshot preflight failed: {exc}", file=sys.stderr)
        return 2
    try:
        _validate_qlora_preflight(
            require_qlora_4bit=bool(args.require_qlora_4bit),
            use_4bit=bool(args.use_4bit),
            base_model=str(args.base_model),
        )
        if not bool(args.prepare_only):
            _validate_qlora_runtime_preflight(
                require_qlora_4bit=bool(args.require_qlora_4bit),
                use_4bit=bool(args.use_4bit),
                base_model=str(args.base_model),
            )
    except ValueError as exc:
        print(f"Training QLoRA preflight failed: {exc}", file=sys.stderr)
        return 2
    run_id = _resolve_run_id(
        run_id=args.run_id,
        base_model=args.base_model,
        snapshot_id=snapshot.snapshot_id,
        package_version=int(args.package_version),
    )
    output_root = Path(args.output_root).resolve()
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    records = _read_retrieval_records(retrieval_corpus_path)
    examples = _build_examples(
        records=records,
        base_model=args.base_model,
        snapshot=snapshot,
        corpus_digest=corpus_digest,
        max_examples=int(args.max_examples),
        refusal_every=int(args.refusal_every),
    )

    examples_path = run_dir / "examples.jsonl"
    _write_examples_jsonl(examples_path, examples)
    examples_digest = _sha256_file(examples_path)

    manifest = {
        "manifest_version": "training-package.v1",
        "generated_at": start_utc,
        "run_id": run_id,
        "base_model": args.base_model,
        "snapshot_manifest_path": snapshot.snapshot_manifest_path,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_sha256": snapshot.snapshot_sha256,
        "retrieval_corpus_path": str(retrieval_corpus_path),
        "retrieval_corpus_digest": corpus_digest,
        "retrieval_corpus_doc_count": corpus_doc_count,
        "training_input_contract_path": str(training_input_contract_path),
        "index_meta_path": str(index_meta_path),
        "qlora_required": bool(args.require_qlora_4bit),
        "requested_use_4bit": bool(args.use_4bit),
        "example_schema_version": "instruction-tuning.v1",
        "example_count": len(examples),
        "examples_path": str(examples_path),
        "examples_sha256": examples_digest,
        "excluded_globs": [
            "eval/*.jsonl",
            "dist/eval/**",
            "tests/fixtures/**",
            "tests/golden/**",
            "Research/**",
            "docs/proposal/**",
        ],
    }
    _write_json(run_dir / "manifest.json", manifest)

    run_config = {
        "schema_version": "training-run-config.v1",
        "run_id": run_id,
        "prepare_only": bool(args.prepare_only),
        "base_model": args.base_model,
        "snapshot_manifest": str(snapshot_manifest) if snapshot_manifest else None,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_sha256": snapshot.snapshot_sha256,
        "retrieval_corpus": str(retrieval_corpus_path),
        "training_input_contract": str(training_input_contract_path),
        "index_meta": str(index_meta_path),
        "qlora": {
            "required": bool(args.require_qlora_4bit),
        },
        "max_examples": int(args.max_examples),
        "refusal_every": int(args.refusal_every),
        "training_hyperparams": {
            "max_seq_len": int(args.max_seq_len),
            "epochs": float(args.epochs),
            "learning_rate": float(args.learning_rate),
            "batch_size": int(args.batch_size),
            "grad_accum": int(args.grad_accum),
            "lora_r": int(args.lora_r),
            "lora_alpha": int(args.lora_alpha),
            "lora_dropout": float(args.lora_dropout),
            "lora_target_modules": [
                token.strip()
                for token in str(args.lora_target_modules).split(",")
                if token.strip()
            ],
            "use_4bit": bool(args.use_4bit),
            "allow_pt_bin": bool(args.allow_pt_bin),
        },
        "smoke": {
            "prompt": str(args.smoke_prompt),
            "max_new_tokens": int(args.smoke_max_new_tokens),
        },
    }
    _write_json(run_dir / "run_config.json", run_config)

    metadata: dict[str, Any] = {
        "schema_version": "training-run-metadata.v1",
        "run_id": run_id,
        "started_at_utc": start_utc,
        "git_head": _git_head(),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "prepare_only": bool(args.prepare_only),
        "artifact_dir": None,
        "smoke_report": None,
        "status": "prepare_only" if args.prepare_only else "pending",
        "qlora": {
            "required": bool(args.require_qlora_4bit),
            "requested_use_4bit": bool(args.use_4bit),
            "effective_use_4bit": None,
            "model_flag_is_loaded_in_4bit": None,
            "quantization_config_load_in_4bit": None,
            "quantization_config_type": None,
            "quantization_config_compute_dtype": None,
            "quantization_config_double_quant": None,
            "evidence_status": "not_executed_prepare_only"
            if args.prepare_only
            else "pending",
        },
    }

    if args.prepare_only:
        metadata["finished_at_utc"] = _utc_now_iso()
        _write_json(run_dir / "run_metadata.json", metadata)
        print(f"Prepared training package at: {run_dir}")
        return 0

    artifact_metrics = _train_adapter(
        base_model=args.base_model,
        examples=examples,
        output_dir=run_dir,
        max_seq_len=int(args.max_seq_len),
        epochs=float(args.epochs),
        learning_rate=float(args.learning_rate),
        batch_size=int(args.batch_size),
        grad_accum=int(args.grad_accum),
        lora_r=int(args.lora_r),
        lora_alpha=int(args.lora_alpha),
        lora_dropout=float(args.lora_dropout),
        lora_target_modules=[
            token.strip()
            for token in str(args.lora_target_modules).split(",")
            if token.strip()
        ],
        use_4bit=bool(args.use_4bit),
        require_qlora_4bit=bool(args.require_qlora_4bit),
        allow_pt_bin=bool(args.allow_pt_bin),
    )
    adapter_dir = run_dir / "adapter"
    _release_torch_memory()

    smoke_report = _run_inference_smoke(
        base_model=args.base_model,
        adapter_dir=adapter_dir,
        prompt=str(args.smoke_prompt),
        max_new_tokens=int(args.smoke_max_new_tokens),
        use_4bit=bool(args.use_4bit),
        allow_pt_bin=bool(args.allow_pt_bin),
    )
    _write_json(run_dir / "inference_smoke.json", smoke_report)

    qlora_metrics = artifact_metrics.get("qlora")
    if isinstance(qlora_metrics, dict):
        qlora_metrics = dict(qlora_metrics)
        qlora_metrics["evidence_status"] = "captured_during_training"
        metadata["qlora"] = qlora_metrics

    metadata.update(
        {
            "status": "completed" if smoke_report.get("pass") else "smoke_failed",
            "artifact_dir": str(adapter_dir),
            "training_metrics": artifact_metrics,
            "smoke_report": str(run_dir / "inference_smoke.json"),
            "finished_at_utc": _utc_now_iso(),
        }
    )
    _write_json(run_dir / "run_metadata.json", metadata)

    print(f"Training run completed at: {run_dir}")
    return 0 if smoke_report.get("pass") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

