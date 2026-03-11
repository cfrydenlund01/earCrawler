from __future__ import annotations

"""Basic local inference smoke check for a fine-tuned adapter artifact."""

import argparse
import json
from pathlib import Path
from typing import Any


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _run_smoke(
    *,
    base_model: str,
    adapter_dir: Path,
    prompt: str,
    max_new_tokens: int,
    allow_pt_bin: bool,
) -> dict[str, Any]:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(str(adapter_dir), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token or tokenizer.unk_token

    model_kwargs: dict[str, Any] = {
        "trust_remote_code": True,
        "use_safetensors": not allow_pt_bin,
    }
    if torch.cuda.is_available():
        model_kwargs["device_map"] = "auto"
        if torch.cuda.is_bf16_supported():
            model_kwargs["torch_dtype"] = torch.bfloat16
        else:
            model_kwargs["torch_dtype"] = torch.float16

    model = AutoModelForCausalLM.from_pretrained(base_model, **model_kwargs)
    model = PeftModel.from_pretrained(model, str(adapter_dir))
    model.eval()

    encoded = tokenizer(prompt, return_tensors="pt")
    device = model.device
    encoded = {key: value.to(device) for key, value in encoded.items()}
    with torch.no_grad():
        generated = model.generate(
            **encoded,
            max_new_tokens=int(max_new_tokens),
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    generated_text = tokenizer.decode(generated[0], skip_special_tokens=True)
    completion = (
        generated_text[len(prompt) :].strip()
        if generated_text.startswith(prompt)
        else generated_text.strip()
    )
    return {
        "base_model": base_model,
        "adapter_dir": str(adapter_dir),
        "prompt": prompt,
        "generated_text": generated_text,
        "completion": completion,
        "pass": bool(completion),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run inference smoke on a trained adapter."
    )
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--adapter-dir", type=Path, required=True)
    parser.add_argument(
        "--prompt",
        default="When is a license required under EAR section 736.2(b)?",
    )
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument(
        "--allow-pt-bin",
        action="store_true",
        help=(
            "Allow loading legacy *.bin model weights. Default requires safetensors "
            "for safer loading behavior."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("dist") / "training" / "inference_smoke.json",
    )
    args = parser.parse_args(argv)

    adapter_dir = args.adapter_dir.resolve()
    if not adapter_dir.exists():
        raise FileNotFoundError(f"Adapter directory not found: {adapter_dir}")

    report = _run_smoke(
        base_model=str(args.base_model),
        adapter_dir=adapter_dir,
        prompt=str(args.prompt),
        max_new_tokens=int(args.max_new_tokens),
        allow_pt_bin=bool(args.allow_pt_bin),
    )
    _write_json(args.out.resolve(), report)
    print(f"Wrote {args.out}")
    return 0 if report.get("pass") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
