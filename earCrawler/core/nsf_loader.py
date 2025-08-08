"""NSF case paragraph loader implementing :class:`CorpusLoader`."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterator

from .corpus_loader import CorpusLoader
from .nsf_case_parser import NSFCaseParser


class NSFLoader(CorpusLoader):
    """Load paragraphs from NSF/ORI case files."""

    def __init__(self, parser: NSFCaseParser, fixtures_dir: Path) -> None:
        self.parser = parser
        self.fixtures_dir = fixtures_dir

    def iterate_paragraphs(self) -> Iterator[Dict[str, object]]:
        cases = self.parser.run(self.fixtures_dir, live=False)
        for case in cases:
            case_number = case.get("case_number", "")
            for idx, para in enumerate(case.get("paragraphs", [])):
                yield {
                    "source": "nsf",
                    "text": para,
                    "identifier": f"{case_number}:{idx}",
                }

    def run(
        self,
        fixtures_dir: Path | None = None,
        live: bool = False,
        output_dir: str | None = None,
    ) -> list[Dict[str, object]]:
        """Return all paragraphs; parameters kept for API parity."""
        if fixtures_dir is not None:
            self.fixtures_dir = fixtures_dir
        return list(self.iterate_paragraphs())
