"""Aggregate per-dimension scores into a final 0-100 score, verdict, and bilingual summary."""
from __future__ import annotations

from app.detector.types import DimensionResult, Verdict

# v0.2 weights (6 dimensions, after the 2026-Q2 relay-poisoning incidents
# that pushed `injection_safety` into the core score). Skipped dimensions
# drop out and the remainder is renormalized.
V01_WEIGHTS: dict[str, float] = {
    "online":               0.10,
    "identity_consistency": 0.20,
    "wrapper_detection":    0.15,
    "token_billing":        0.15,
    "tool_use":             0.20,
    "injection_safety":     0.20,
}


def aggregate(results: dict[str, DimensionResult]) -> tuple[int, Verdict]:
    online = results.get("online")
    if online is not None and (online.status == "missing" or online.score == 0):
        return 0, "offline"

    weighted_sum = 0.0
    weight_total = 0.0
    for name, weight in V01_WEIGHTS.items():
        r = results.get(name)
        if r is None or r.status == "skipped":
            continue
        weighted_sum += r.score * weight
        weight_total += weight

    if weight_total == 0:
        return 0, "offline"

    score = round(weighted_sum / weight_total)

    if score >= 90:
        verdict: Verdict = "authentic"
    elif score >= 75:
        verdict = "likely_authentic"
    elif score >= 50:
        verdict = "suspicious"
    else:
        verdict = "likely_fake"

    return score, verdict


_VERDICT_BLURB_ZH = {
    "authentic":         "模型行为高度自洽，符合官方特征。",
    "likely_authentic":  "模型行为大致正常，存在轻微偏差。",
    "suspicious":        "存在多处可疑指标，建议谨慎使用。",
    "likely_fake":       "强烈怀疑模型被替换或能力被阉割。",
    "offline":           "上游接口不可达，无法完成检测。",
}
_VERDICT_BLURB_EN = {
    "authentic":         "Model behavior is highly consistent with official baselines.",
    "likely_authentic":  "Model behavior is mostly correct with minor deviations.",
    "suspicious":        "Several indicators look suspicious; use with caution.",
    "likely_fake":       "Strong evidence the model has been swapped or crippled.",
    "offline":           "Upstream is unreachable; detection could not run.",
}


def summarize(
    results: dict[str, DimensionResult],
    *,
    score: int,
    verdict: Verdict,
    model: str,
) -> tuple[str, str]:
    """Generate bilingual summary by composing per-dimension findings — no LLM call."""
    zh_parts = [_VERDICT_BLURB_ZH[verdict]]
    en_parts = [_VERDICT_BLURB_EN[verdict]]

    # Highlight worst dimension (excluding skipped/online)
    candidates = [
        r for n, r in results.items()
        if n != "online" and r.status not in ("skipped",)
    ]
    if candidates:
        worst = min(candidates, key=lambda r: r.score)
        if worst.score < 70:
            zh_parts.append(f"最弱维度：{worst.name}（{worst.score} 分）。")
            en_parts.append(f"Weakest dimension: {worst.name} (score {worst.score}).")

    zh_parts.append(f"目标模型：{model}，综合得分 {score}/100。")
    en_parts.append(f"Target model: {model}, overall score {score}/100.")

    return " ".join(zh_parts), " ".join(en_parts)
