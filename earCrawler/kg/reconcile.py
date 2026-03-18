"""Deterministic entity reconciliation engine.

The implementation is intentionally lightweight but captures the key concepts
required for the tests:

* Normalisation pipeline combining case folding, Unicode NFC, punctuation
  stripping, whitespace collapsing and simple stop word removal.
* Basic blocking key generation.
* Feature scoring with explainable contributions and configurable weights.
* Threshold based decisions with hard country constraint plus whitelist and
  blacklist overrides.
* Emission of audit artefacts (id map, decisions log, summary and conflicts
  report, and merge triples).

The module is deterministic; inputs are processed in sorted order and no random
state is used.
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import unicodedata
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Tuple
import os

from rapidfuzz.distance import JaroWinkler


STOPWORDS = {
    "inc",
    "corp",
    "corporation",
    "ltd",
    "llc",
    "company",
}


@dataclass
class Entity:
    """Minimal representation of a source entity."""

    id: str
    name: str
    country: str
    source: str
    duns: str | None = None
    cage: str | None = None
    fr_doc: str | None = None
    url: str | None = None


# ---------------------------------------------------------------------------
# Normalisation and blocking


def normalize(text: str) -> str:
    """Normalise a string deterministically."""

    text = unicodedata.normalize("NFC", text or "")
    text = text.casefold()
    text = re.sub(r"[^\w\s]", " ", text)
    text = " ".join(text.split())
    tokens = [t for t in text.split() if t and t not in STOPWORDS]
    return " ".join(tokens)


def _soundex(s: str) -> str:
    """Very small soundex style key used only for blocking."""

    if not s:
        return ""
    s = s.upper()
    first, tail = s[0], s[1:]
    mapping = {
        "BFPV": "1",
        "CGJKQSXZ": "2",
        "DT": "3",
        "L": "4",
        "MN": "5",
        "R": "6",
    }
    trans: Dict[str, str] = {}
    for chars, val in mapping.items():
        for c in chars:
            trans[c] = val
    digits = [trans.get(c, "") for c in tail]
    key = first + "".join(digits)
    return key[:4].ljust(4, "0")


def blocking_keys(e: Entity) -> Dict[str, str]:
    name_norm = normalize(e.name)
    tokens = name_norm.split()
    alnum = re.sub(r"[^0-9a-z]", "", name_norm)
    return {
        "soundex": _soundex(name_norm),
        "alnum": alnum,
        "country_name": f"{e.country}-{alnum}",
        "country_soundex": f"{e.country}-{_soundex(name_norm)}",
        "country_token0": f"{e.country}-{tokens[0]}" if tokens else "",
    }


# ---------------------------------------------------------------------------
# Rules loading


def load_rules(path: Path) -> dict:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    wl_path = path.parent / "whitelist.csv"
    bl_path = path.parent / "blacklist.csv"
    with wl_path.open("r", encoding="utf-8") as whitelist_handle:
        data["whitelist"] = {
            (row["left_id"], row["right_id"]): row["reason"]
            for row in csv.DictReader(whitelist_handle)
        }
    with bl_path.open("r", encoding="utf-8") as blacklist_handle:
        data["blacklist"] = {
            (row["left_id"], row["right_id"]): row["reason"]
            for row in csv.DictReader(blacklist_handle)
        }
    return data


def load_corpus(path: Path) -> List[Entity]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entities = [Entity(**e) for e in raw]
    entities.sort(key=lambda e: e.id)
    return entities


# ---------------------------------------------------------------------------
# Scoring


def _token_set(name: str) -> set[str]:
    return set(normalize(name).split())


def _host(url: str | None) -> str | None:
    if not url:
        return None
    m = re.match(r"https?://([^/]+)/?", url)
    return m.group(1).lower() if m else None


def score_pair(a: Entity, b: Entity, rules: dict) -> Tuple[float, dict]:
    weights = rules.get("weights", {})
    feats: Dict[str, float] = {}

    name_a = normalize(a.name)
    name_b = normalize(b.name)
    feats["name_exact"] = float(name_a == name_b)
    ta, tb = _token_set(a.name), _token_set(b.name)
    feats["token_jaccard"] = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    feats["jaro_winkler"] = JaroWinkler.normalized_similarity(name_a, name_b)
    feats["prefix_overlap"] = float(
        len(os.path.commonprefix([name_a, name_b])) / max(len(name_a), len(name_b))
        if name_a and name_b
        else 0.0
    )
    feats["suffix_overlap"] = float(
        len(os.path.commonprefix([name_a[::-1], name_b[::-1]]))
        / max(len(name_a), len(name_b))
        if name_a and name_b
        else 0.0
    )
    feats["country_match"] = float(a.country == b.country)

    id_equal = 0.0
    for attr in ("duns", "cage", "fr_doc"):
        va, vb = getattr(a, attr), getattr(b, attr)
        if va and vb and va == vb:
            id_equal = 1.0
            break
    feats["id_equal"] = id_equal
    feats["url_host"] = float(_host(a.url) == _host(b.url) and _host(a.url) is not None)

    source_bonus = rules.get("sources", {}).get(a.source, 0.0) + rules.get(
        "sources", {}
    ).get(b.source, 0.0)
    feats["source_bonus"] = source_bonus

    details = {
        k: {
            "value": v,
            "weight": weights.get(k, 0.0),
            "contribution": v * weights.get(k, 0.0),
        }
        for k, v in feats.items()
    }
    score = sum(d["contribution"] for d in details.values())
    return score, details


# ---------------------------------------------------------------------------
# Reconciliation


def _apply_overrides(
    left: str, right: str, rules: dict
) -> Tuple[str | None, str | None]:
    pair = (left, right)
    if pair in rules.get("whitelist", {}):
        return "auto_merge", rules["whitelist"][pair]
    if pair in rules.get("blacklist", {}):
        return "reject", rules["blacklist"][pair]
    return None, None


def _candidate_pair_indices_all_pairs(entity_count: int) -> List[Tuple[int, int]]:
    return list(combinations(range(entity_count), 2))


def _candidate_pair_indices_blocked(
    entities: List[Entity], rules: dict
) -> List[Tuple[int, int]]:
    blocking_cfg = rules.get("blocking", {})
    lexical_keys = blocking_cfg.get(
        "lexical_keys",
        ["country_name", "alnum", "country_soundex", "country_token0"],
    )
    max_lexical_block_size = int(blocking_cfg.get("max_lexical_block_size", 64))

    buckets: Dict[Tuple[str, str], List[int]] = {}

    for idx, entity in enumerate(entities):
        keys = blocking_keys(entity)
        for key_name in lexical_keys:
            value = keys.get(key_name, "")
            if value:
                buckets.setdefault((f"lexical:{key_name}", value), []).append(idx)

        for attr in ("duns", "cage", "fr_doc"):
            value = getattr(entity, attr)
            if value:
                buckets.setdefault((f"id:{attr}", value), []).append(idx)

        host = _host(entity.url)
        if host:
            buckets.setdefault(("url_host", host), []).append(idx)

    pairs: set[Tuple[int, int]] = set()
    for (bucket_type, _bucket_value), members in buckets.items():
        uniq_members = sorted(set(members))
        if len(uniq_members) < 2:
            continue
        if bucket_type.startswith("lexical:") and len(uniq_members) > max_lexical_block_size:
            continue
        for left_idx, right_idx in combinations(uniq_members, 2):
            pairs.add((left_idx, right_idx))

    return sorted(
        pairs,
        key=lambda pair: (entities[pair[0]].id, entities[pair[1]].id),
    )


def candidate_pair_indices(
    entities: List[Entity], rules: dict, *, candidate_mode: str = "blocked"
) -> List[Tuple[int, int]]:
    if candidate_mode == "all_pairs":
        return _candidate_pair_indices_all_pairs(len(entities))
    if candidate_mode == "blocked":
        return _candidate_pair_indices_blocked(entities, rules)
    raise ValueError(f"Unsupported candidate mode: {candidate_mode}")


def reconcile_pairs(
    entities: List[Entity], rules: dict, *, candidate_mode: str = "blocked"
) -> dict:
    high = float(rules["thresholds"]["high"])
    low = float(rules["thresholds"]["low"])

    decisions: List[dict] = []
    counts = {"auto_merge": 0, "review": 0, "reject": 0}
    feature_totals: Dict[str, float] = {}
    canonical: Dict[str, str] = {e.id: e.id for e in entities}

    pair_indices = candidate_pair_indices(entities, rules, candidate_mode=candidate_mode)
    for left_idx, right_idx in pair_indices:
        left = entities[left_idx]
        right = entities[right_idx]
        decision, reason = _apply_overrides(left.id, right.id, rules)
        score, feats = score_pair(left, right, rules)
        if decision is None:
            if feats["country_match"]["value"] < 1.0:
                decision = "reject"
                reason = "country mismatch"
            elif score >= high:
                decision = "auto_merge"
            elif score >= low:
                decision = "review"
            else:
                decision = "reject"
        if decision == "auto_merge":
            canon = canonical[left.id]
            canonical[right.id] = canon
        counts[decision] += 1
        for name, detail in feats.items():
            feature_totals[name] = feature_totals.get(name, 0.0) + detail["value"]
        decisions.append(
            {
                "left": left.id,
                "right": right.id,
                "score": score,
                "decision": decision,
                "reason": reason,
                "features": feats,
            }
        )

    feature_avgs = {
        k: (feature_totals[k] / len(decisions) if decisions else 0.0)
        for k in sorted(feature_totals)
    }

    all_pairs_total = len(entities) * (len(entities) - 1) // 2
    evaluated_pairs = len(pair_indices)
    pair_stats = {
        "candidate_mode": candidate_mode,
        "all_pairs_total": all_pairs_total,
        "candidate_pairs_evaluated": evaluated_pairs,
        "candidate_reduction_ratio": (
            (all_pairs_total - evaluated_pairs) / all_pairs_total
            if all_pairs_total
            else 0.0
        ),
    }

    summary = {
        "counts": counts,
        "thresholds": {"high": high, "low": low},
        "feature_avgs": feature_avgs,
        "pair_stats": pair_stats,
    }
    return {
        "summary": summary,
        "decisions": decisions,
        "canonical": canonical,
    }


def reconcile(
    entities: List[Entity],
    rules: dict,
    out_dir: Path,
    *,
    candidate_mode: str = "blocked",
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = Path("kg/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    Path("kg/delta").mkdir(parents=True, exist_ok=True)

    result = reconcile_pairs(entities, rules, candidate_mode=candidate_mode)
    summary = result["summary"]
    decisions = result["decisions"]
    canonical = result["canonical"]

    # Emit audit artefacts -------------------------------------------------
    with gzip.open(out_dir / "decisions.jsonl.gz", "wt", encoding="utf-8") as fh:
        for d in decisions:
            fh.write(json.dumps(d, sort_keys=True) + "\n")

    # idmap
    idmap_path = out_dir / "idmap.csv"
    with idmap_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["canonical_id", "source_id"])
        for sid, cid in sorted(canonical.items(), key=lambda x: (x[1], x[0])):
            w.writerow([cid, sid])

    # TTL merges
    ttl_path = Path("kg/delta/reconcile-merged.ttl")
    with ttl_path.open("w", encoding="utf-8") as fh:
        fh.write(
            """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
"""
        )
        for sid, cid in canonical.items():
            if sid != cid:
                fh.write(f"<urn:entity:{cid}> owl:sameAs <urn:entity:{sid}> .\n")

    (reports_dir / "reconcile-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )

    conflicts = [d for d in decisions if d["decision"] != "auto_merge"]
    (reports_dir / "reconcile-conflicts.json").write_text(
        json.dumps(conflicts, indent=2, sort_keys=True), encoding="utf-8"
    )

    return summary


# The module exposes functions used by the CLI and tests: normalize,
# blocking_keys, load_rules, load_corpus, score_pair, candidate_pair_indices,
# reconcile_pairs and reconcile.
