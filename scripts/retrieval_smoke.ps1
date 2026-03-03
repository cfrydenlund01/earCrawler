param(
  [string]$Python = "py"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

Push-Location $repoRoot
try {
  New-Item -ItemType Directory -Force -Path ".pytest_tmp_local\retrieval_smoke" | Out-Null
  & $Python -m pytest -q tests/rag/test_retriever.py --basetemp .pytest_tmp_local\retrieval_smoke -k "windows_default_backend_uses_bruteforce_without_faiss or faiss_backend_breaks_ties_deterministically_on_windows"

  @'
import importlib
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import earCrawler.rag.retriever as retriever_mod


class KeywordModel:
    def __init__(self, _name: str) -> None:
        self.calls = []

    def _encode_one(self, text: str):
        lowered = str(text or "").lower()
        if "license" in lowered:
            return np.array([1.0, 0.0, 0.0], dtype="float32")
        if "prohibition" in lowered:
            return np.array([0.0, 1.0, 0.0], dtype="float32")
        return np.array([0.0, 0.0, 1.0], dtype="float32")

    def encode(self, texts, show_progress_bar=False):
        self.calls.append(list(texts))
        return np.asarray([self._encode_one(text) for text in texts], dtype="float32")


importlib.reload(retriever_mod)
retriever_mod.SentenceTransformer = lambda name: KeywordModel(name)
retriever_mod.faiss = None
retriever_mod.sys.platform = "win32"
os.environ.pop("EARCRAWLER_RETRIEVAL_BACKEND", None)

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    rows = [
        {
            "doc_id": "EAR-740.9",
            "section_id": "EAR-740.9",
            "text": "License exception STA eligibility.",
            "chunk_kind": "section",
            "source": "smoke",
            "source_ref": "retrieval_smoke",
        },
        {
            "doc_id": "EAR-740.1",
            "section_id": "EAR-740.1",
            "text": "License exception overview.",
            "chunk_kind": "section",
            "source": "smoke",
            "source_ref": "retrieval_smoke",
        },
        {
            "doc_id": "EAR-736.2",
            "section_id": "EAR-736.2",
            "text": "General prohibition one.",
            "chunk_kind": "section",
            "source": "smoke",
            "source_ref": "retrieval_smoke",
        },
    ]
    index_path = tmp_path / "windows.faiss"
    meta_path = index_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps({"rows": rows}, indent=2) + "\n", encoding="utf-8")

    retriever = retriever_mod.Retriever(
        SimpleNamespace(),
        SimpleNamespace(),
        model_name="stub-model",
        index_path=index_path,
    )
    first = retriever.query("license exception", k=2)
    second = retriever.query("license exception", k=2)
    first_ids = [row.get("doc_id") for row in first]
    second_ids = [row.get("doc_id") for row in second]
    config = retriever_mod.describe_retriever_config(retriever)

    print(f"backend={config.get('backend')}")
    print("top_k_ids=" + ",".join(str(value) for value in first_ids))
    if first_ids != second_ids:
        raise SystemExit("determinism_check=failed")
    print("determinism_check=passed")
'@ | & $Python -
}
finally {
  Pop-Location
}
