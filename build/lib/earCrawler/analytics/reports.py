from __future__ import annotations

"""Corpus-level analytics utilities."""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple


def load_corpus(source: str, data_dir: Path = Path("data")) -> Iterator[Dict]:
    """Read data/{source}_corpus.jsonl and yield each record dict."""
    path = data_dir / f"{source}_corpus.jsonl"
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def top_entities(source: str, entity_type: str, n: int = 10) -> List[Tuple[str, int]]:
    """Count ORG|PERSON|GRANT across paragraphs and return top n."""
    counter = Counter()
    for record in load_corpus(source):
        for entity in record.get("entities", {}).get(entity_type, []):
            counter[entity] += 1
    return counter.most_common(n)


def term_frequency(source: str, n: int = 20) -> List[Tuple[str, int]]:
    """Compute word frequencies (normalized) across paragraphs and return top n."""
    counter = Counter()
    for record in load_corpus(source):
        paragraph = record.get("paragraph", "")
        for word in paragraph.split():
            normalized = "".join(ch for ch in word.lower() if ch.isalnum())
            if normalized:
                counter[normalized] += 1
    return counter.most_common(n)


def cooccurrence(source: str, entity_type: str) -> Dict[str, Set[str]]:
    """Build a co-occurrence map of entities within the same paragraph."""
    mapping: Dict[str, Set[str]] = defaultdict(set)
    for record in load_corpus(source):
        entities = set(record.get("entities", {}).get(entity_type, []))
        for entity in entities:
            others = entities - {entity}
            if others:
                mapping[entity].update(others)
            else:
                mapping.setdefault(entity, set())
    return mapping
