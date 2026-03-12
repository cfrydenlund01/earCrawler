from __future__ import annotations

from typing import Mapping


def build_eval_markdown_lines(
    *,
    accuracy: float,
    label_accuracy: float,
    unanswerable_accuracy: float,
    grounded_rate: float,
    avg_latency: float,
    dataset_id: str,
    dataset_task: object,
    provider: str,
    model: str,
    num_items: int,
    top_k: int,
    retrieval_mode: str,
    ablation_mode: str | None,
    kg_expansion_enabled: bool | None,
    primary_metric: str,
    answer_score_mode: str,
    semantic_threshold: float,
    kg_digest: str | None,
    evidence_coverage_recall: float,
    multihop_items: int,
    multihop_evidence_coverage_recall: float,
    kg_path_usage_rate: float,
    multihop_trace_pass_rate: float,
    citation_presence_rate: float,
    citation_valid_citation_rate: float,
    citation_supported_rate: float,
    citation_overclaim_rate: float,
    citation_micro_precision: float,
    citation_micro_recall: float,
    citation_micro_f1: float,
    fallbacks_used: int,
    fallback_max_uses: int | None,
    fallback_threshold_breached: bool,
    fallback_counts_dict: Mapping[str, int],
    by_task: Mapping[str, Mapping[str, float]],
    semantic_enabled: bool,
    semantic_accuracy: float,
) -> list[str]:
    lines = [
        "| Accuracy | Label Accuracy | Unanswerable Accuracy | Grounded Rate | Avg Latency (s) |",
        "|---------:|---------------:|----------------------:|--------------:|----------------:|",
        f"| {accuracy:.4f} | {label_accuracy:.4f} | {unanswerable_accuracy:.4f} | {grounded_rate:.4f} | {avg_latency:.4f} |",
        "",
        f"- Dataset: {dataset_id} (task={dataset_task})",
        f"- Provider/model: {provider} / {model}",
        f"- Items: {num_items}, top_k={top_k}",
        f"- Retrieval mode: {retrieval_mode}",
        f"- Ablation: {ablation_mode or 'none'} (kg_expansion={kg_expansion_enabled})",
        f"- Primary metric: {primary_metric}",
        f"- Answer scoring: {answer_score_mode}"
        + (
            f" (threshold={semantic_threshold:.2f})"
            if answer_score_mode == "semantic"
            else ""
        ),
        f"- KG digest: {kg_digest or 'n/a'}",
        f"- Evidence coverage recall: {evidence_coverage_recall:.4f}",
        f"- Multi-hop: count={multihop_items}, evidence_recall={multihop_evidence_coverage_recall:.4f}, "
        f"kg_path_usage={kg_path_usage_rate:.4f}, trace_pack_pass_rate={multihop_trace_pass_rate:.4f}",
        f"- Citations: presence={citation_presence_rate:.4f}, "
        f"valid_citation={citation_valid_citation_rate:.4f}, "
        f"supported={citation_supported_rate:.4f}, "
        f"overclaim={citation_overclaim_rate:.4f}",
        f"- Citation micro: precision={citation_micro_precision:.4f}, "
        f"recall={citation_micro_recall:.4f}, f1={citation_micro_f1:.4f}",
        f"- Eval strictness: fallbacks_used={fallbacks_used}, "
        f"fallback_max_uses={fallback_max_uses if fallback_max_uses is not None else 'disabled'}, "
        f"threshold_breached={fallback_threshold_breached}",
    ]
    if fallback_counts_dict:
        lines.append(
            "- Fallback counts: "
            + ", ".join(f"{k}={v}" for k, v in sorted(fallback_counts_dict.items()))
        )
    if by_task:
        lines.append("")
        lines.append("By-task summary:")
        for task_name, stats in sorted(by_task.items()):
            lines.append(
                f"- {task_name}: accuracy={stats['accuracy']:.4f}, "
                f"label_accuracy={stats['label_accuracy']:.4f}, "
                f"grounded_rate={stats['grounded_rate']:.4f}, "
                f"count={int(stats['count'])}"
            )
    if semantic_enabled:
        lines.append("")
        lines.append(
            f"- Semantic accuracy (SequenceMatcher >={semantic_threshold:.2f}): {semantic_accuracy:.4f}"
        )
    return lines

