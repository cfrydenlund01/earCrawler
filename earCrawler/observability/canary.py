from __future__ import annotations

"""Evaluation helpers for canary probes."""

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class CanaryBudget:
    """Simple latency and row-count expectations for a canary probe."""

    max_latency_ms: float
    min_rows: int = 0
    expect_status: int = 200


@dataclass(slots=True)
class CanaryResult:
    name: str
    ok: bool
    latency_ms: float
    observed_rows: int
    status_code: Optional[int]
    message: str

    @property
    def status(self) -> str:
        return "pass" if self.ok else "fail"


def evaluate_canary_response(
    *,
    name: str,
    latency_ms: float,
    observed_rows: int,
    status_code: Optional[int],
    budget: CanaryBudget,
) -> CanaryResult:
    """Return a structured evaluation of a probe outcome."""

    message_parts: list[str] = []
    ok = True
    if status_code is not None and budget.expect_status and status_code != budget.expect_status:
        ok = False
        message_parts.append(f"status {status_code} != expected {budget.expect_status}")
    if latency_ms > budget.max_latency_ms:
        ok = False
        message_parts.append(f"latency {latency_ms:.2f}ms > {budget.max_latency_ms}ms budget")
    if observed_rows < budget.min_rows:
        ok = False
        message_parts.append(f"rows {observed_rows} < min {budget.min_rows}")
    if not message_parts:
        message_parts.append("within budget")
    return CanaryResult(
        name=name,
        ok=ok,
        latency_ms=latency_ms,
        observed_rows=observed_rows,
        status_code=status_code,
        message="; ".join(message_parts),
    )


__all__ = ["CanaryBudget", "CanaryResult", "evaluate_canary_response"]
