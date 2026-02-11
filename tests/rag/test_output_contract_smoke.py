from __future__ import annotations

import pytest

from earCrawler.rag.output_schema import (
    DEFAULT_ALLOWED_LABELS,
    OutputSchemaError,
    validate_and_extract_strict_answer,
)


def test_contract_smoke_invalid_json_fails_loudly() -> None:
    with pytest.raises(OutputSchemaError) as exc_info:
        validate_and_extract_strict_answer(
            "not-json",
            allowed_labels=DEFAULT_ALLOWED_LABELS,
            context="[EAR-734.3] Example EAR passage text.",
        )

    err = exc_info.value
    assert err.code == "invalid_json"
    payload = err.as_dict()
    assert payload["code"] == "invalid_json"
    assert payload["details"].get("pos") == 0
