from __future__ import annotations

import re
from typing import Mapping, Sequence

_CFR_CITATION_RE = re.compile(
    r"(?:§\s*)?(?P<section>\d{3}\.\d+(?:\([A-Za-z0-9]+\))*)",
    flags=re.IGNORECASE,
)


def extract_ear_section_targets(prompt: str) -> list[str]:
    """Extract deterministic EAR section targets from explicit CFR citations."""

    raw = str(prompt or "")
    seen: set[str] = set()
    targets: list[str] = []
    for match in _CFR_CITATION_RE.finditer(raw):
        sec = str(match.group("section") or "").strip()
        if not sec:
            continue
        exact = f"EAR-{sec}"
        if exact not in seen:
            targets.append(exact)
            seen.add(exact)
        if "(" in sec:
            base = f"EAR-{sec.split('(', 1)[0]}"
            if base not in seen:
                targets.append(base)
                seen.add(base)
    return targets


def canonical_section_id(row: Mapping[str, object]) -> str | None:
    raw = row.get("section_id") or row.get("section") or row.get("doc_id") or row.get("id")
    if raw is None:
        return None
    sec = str(raw).strip()
    if not sec:
        return None
    if sec.upper().startswith("EAR-"):
        if "#" in sec:
            sec = sec.split("#", 1)[0].strip()
        return sec
    return None


def _best_metadata_row_for_section(
    metadata: Sequence[Mapping[str, object]], target_section_id: str
) -> dict[str, object] | None:
    best: Mapping[str, object] | None = None
    best_score = -1_000_000
    target = str(target_section_id or "").strip()
    if not target:
        return None

    for row in metadata:
        sec = canonical_section_id(row)
        if sec != target:
            continue
        doc_id = str(row.get("doc_id") or "")
        chunk_kind = str(row.get("chunk_kind") or "")
        ordinal_raw = row.get("ordinal")
        try:
            ordinal = int(ordinal_raw) if ordinal_raw is not None else None
        except Exception:
            ordinal = None

        score = 0
        if doc_id == target:
            score += 100
        elif doc_id.startswith(target + "#"):
            score += 60
        if chunk_kind == "section":
            score += 10
        if ordinal == 0:
            score += 5
        if score > best_score:
            best = row
            best_score = score

    if best is None:
        return None
    chosen = dict(best)
    chosen.setdefault("section_id", target)
    return chosen


def apply_citation_boost(
    prompt: str,
    *,
    results: list[dict],
    metadata: list[dict],
    k: int,
) -> list[dict]:
    """Ensure explicitly cited sections appear in top-K retrieval results."""

    targets = extract_ear_section_targets(prompt)
    if not targets:
        return results

    present_sections: set[str] = set()
    for row in results:
        sec = canonical_section_id(row) or canonical_section_id({"doc_id": row.get("doc_id")})
        if sec:
            present_sections.add(sec)

    boosted: list[dict] = []
    for target in targets:
        if target in present_sections:
            continue
        row = _best_metadata_row_for_section(metadata, target)
        if row is None:
            continue
        boosted.append(dict(row))
        present_sections.add(target)

    if not boosted:
        return results

    max_score = 0.0
    for row in results:
        try:
            val = float(row.get("score") or 0.0)
        except Exception:
            val = 0.0
        if val > max_score:
            max_score = val

    bump = max_score + 1.0
    for idx, row in enumerate(boosted):
        row.pop("row_id", None)
        row.setdefault("boost_reason", "explicit_citation")
        row["score"] = bump - (idx * 0.001)

    return (boosted + list(results))[: max(1, int(k))]

