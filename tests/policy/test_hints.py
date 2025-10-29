from __future__ import annotations

import json
from pathlib import Path

from earCrawler.policy import load_hints, hints_manifest


def test_load_hints_respects_priority(tmp_path: Path) -> None:
    hints_file = tmp_path / "hints.yml"
    hints_file.write_text(
        """
hints:
  - part: "734"
    program: "BIS Entity List"
    priority: 0.9
    rationale: "Test"
  - part: "736"
    program: "Denied"
    priority: 0.7
    rationale: "Test"
""",
        encoding="utf-8",
    )
    hints = load_hints(hints_file)
    assert len(hints) == 2
    assert hints[0].priority == 0.9

    manifest = json.loads(hints_manifest(hints))
    assert manifest[0]["part"] == "734"
