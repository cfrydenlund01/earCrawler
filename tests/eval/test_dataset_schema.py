from pathlib import Path

from eval.validate_datasets import validate_datasets


def test_eval_datasets_conform_to_schema() -> None:
    issues = validate_datasets(
        manifest_path=Path("eval") / "manifest.json",
        schema_path=Path("eval") / "schema.json",
        dataset_ids=None,
    )
    assert issues == []
