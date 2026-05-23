"""Track per-detection USD spend and abort when over budget."""
from dataclasses import dataclass, field

# Approximate USD per 1M tokens. Source: vendor official pricing as of 2026-05.
# Used only as a coarse safety guard — exact billing happens upstream.
PRICING_PER_MTOK = {
    "claude-opus-4-7":   (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "gpt-5-5":           (1.25, 10.0),
    "gpt-5-4":           (2.5, 10.0),
    "gemini-3-1-pro":    (3.5, 21.0),
}
DEFAULT_PRICING = (5.0, 25.0)  # conservative fallback


class BudgetExceeded(Exception):
    """Raised by BudgetTracker.charge when a charge would push spend past the budget."""


@dataclass
class BudgetTracker:
    budget_usd: float
    spent_usd: float = 0.0
    charges: list[dict] = field(default_factory=list)

    def charge(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        in_price, out_price = PRICING_PER_MTOK.get(model, DEFAULT_PRICING)
        cost = (prompt_tokens / 1_000_000) * in_price + (
            completion_tokens / 1_000_000
        ) * out_price
        new_spent = self.spent_usd + cost
        if new_spent > self.budget_usd:
            raise BudgetExceeded(
                f"budget {self.budget_usd:.4f} USD exceeded "
                f"(would be {new_spent:.4f} USD after this charge)"
            )
        self.spent_usd = new_spent
        self.charges.append(
            {
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_usd": cost,
            }
        )
        return cost

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.budget_usd - self.spent_usd)
