from __future__ import annotations

"""Canonical namespaces for the EAR knowledge graph.

This module is the single source of truth for namespace strings used by KG
generation, validation, and dataset grounding/citation alignment.
"""

from rdflib import Namespace

# Canonical namespaces (normative).
SCHEMA_NS = "https://ear.example.org/schema#"
RESOURCE_NS = "https://ear.example.org/resource/"
GRAPH_NS = "https://ear.example.org/graph/"

# Canonical resource sub-namespaces used across the repo.
ENTITY_NS = "https://ear.example.org/entity/"
PART_NS = "https://ear.example.org/part/"
ANCHOR_NS = "https://ear.example.org/anchor/"
POLICY_HINT_NS = "https://ear.example.org/policyHint/"

# Legacy namespaces to be phased out (but still accepted via explicit mapping).
LEGACY_NS_LIST: list[str] = [
    "https://example.org/ear#",
    "https://example.org/entity#",
    "http://example.org/ear/",
]

# rdflib Namespace helpers.
EAR = Namespace(SCHEMA_NS)
RES = Namespace(RESOURCE_NS)
ENT = Namespace(ENTITY_NS)
PART = Namespace(PART_NS)
ANCH = Namespace(ANCHOR_NS)
HINT = Namespace(POLICY_HINT_NS)

__all__ = [
    "SCHEMA_NS",
    "RESOURCE_NS",
    "GRAPH_NS",
    "ENTITY_NS",
    "PART_NS",
    "ANCHOR_NS",
    "POLICY_HINT_NS",
    "LEGACY_NS_LIST",
    "EAR",
    "RES",
    "ENT",
    "PART",
    "ANCH",
    "HINT",
]

