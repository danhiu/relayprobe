import pytest

from app.detector.budget import BudgetExceeded, BudgetTracker


def test_charge_accumulates_cost():
    bt = BudgetTracker(budget_usd=1.0)
    # claude-opus-4-7 pricing: $15/MTok input, $75/MTok output (placeholder values)
    bt.charge(model="claude-opus-4-7", prompt_tokens=1000, completion_tokens=500)
    assert bt.spent_usd > 0
    assert bt.spent_usd < 1.0


def test_charge_raises_when_over_budget():
    bt = BudgetTracker(budget_usd=0.001)
    with pytest.raises(BudgetExceeded):
        bt.charge(
            model="claude-opus-4-7", prompt_tokens=10000, completion_tokens=10000
        )


def test_unknown_model_uses_default_pricing():
    bt = BudgetTracker(budget_usd=1.0)
    # should not crash; uses fallback price
    bt.charge(model="some-unknown-model", prompt_tokens=100, completion_tokens=100)
    assert bt.spent_usd > 0


def test_remaining_reflects_charges():
    bt = BudgetTracker(budget_usd=1.0)
    bt.charge(model="claude-opus-4-7", prompt_tokens=100, completion_tokens=50)
    assert bt.remaining_usd == bt.budget_usd - bt.spent_usd
    assert bt.remaining_usd >= 0
