"""Pure, manual-only option buying risk calculator. Never submits orders."""
from dataclasses import dataclass
from decimal import Decimal


def money(value):
    amount = Decimal(str(value))
    if not amount.is_finite():
        raise ValueError("Amounts must be finite")
    return amount


@dataclass(frozen=True)
class RiskAssessment:
    decision: str
    reason: str
    investment: Decimal
    planned_loss: Decimal
    potential_profit: Decimal
    return_pct: Decimal
    reward_risk: Decimal
    maximum_investment: Decimal
    allowed_risk: Decimal


def assess_long_option(*, capital, entry, stop, target, lot_size,
                       estimated_total_costs=0, remaining_daily_risk=None,
                       max_trade_risk_pct=Decimal("0.06"),
                       max_investment_pct=Decimal("0.30"),
                       min_reward_risk=Decimal("2")) -> RiskAssessment:
    """All prices per option unit; costs include round-trip fees and slippage.

    Lot size must come from current broker/exchange contract metadata.
    Default limits: 30% capital allocated, 6% capital planned loss per trade.\n    These are user-selected limits, not safe-loss guarantees.\n    The planned stop is not guaranteed; actual losses can be larger.
    """
    capital, entry, stop, target = map(money, (capital, entry, stop, target))
    costs = money(estimated_total_costs)
    risk_pct = money(max_trade_risk_pct)
    min_rr = money(min_reward_risk)
    investment_pct = money(max_investment_pct)
    if type(lot_size) is not int or lot_size <= 0:
        raise ValueError("lot_size must be a positive integer")
    if not (capital > 0 and entry > stop >= 0 and target > entry):
        raise ValueError("Require capital > 0 and 0 <= stop < entry < target")
    if costs < 0 or not (0 < risk_pct <= 1) or not (0 < investment_pct <= 1) or min_rr <= 0:
        raise ValueError("Invalid costs or risk settings")

    investment = entry * lot_size
    loss = (entry - stop) * lot_size + costs
    profit = (target - entry) * lot_size - costs
    reward_risk = profit / loss
    roi = profit / investment * 100
    allowed_risk = capital * risk_pct
    if remaining_daily_risk is not None:
        remaining = money(remaining_daily_risk)
        allowed_risk = min(allowed_risk, max(Decimal(0), remaining))

    max_investment = capital * investment_pct
    if investment + costs > max_investment:
        decision, reason = "NO_TRADE", "INVESTMENT_LIMIT_EXCEEDED"
    elif investment + costs > capital:
        decision, reason = "NO_TRADE", "INSUFFICIENT_CAPITAL"
    elif loss > allowed_risk:
        decision, reason = "NO_TRADE", "RISK_LIMIT_EXCEEDED"
    elif profit <= 0 or reward_risk < min_rr:
        decision, reason = "NO_TRADE", "REWARD_RISK_TOO_LOW"
    else:
        decision, reason = "ELIGIBLE_FOR_MANUAL_REVIEW", "RISK_CHECKS_PASSED"

    return RiskAssessment(decision, reason, investment, loss, profit, roi, reward_risk,
                          max_investment, allowed_risk)
