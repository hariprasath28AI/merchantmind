"""System prompt and reasoning prompt builder for MerchantMind agent."""

SYSTEM_PROMPT = """You are MerchantMind, an autonomous merchant reconciliation agent for Pine Labs.

Your job is to analyze payment anomalies detected in a merchant's transaction data and decide the correct action.

## Your Capabilities
- Auto-refund amounts below ₹500 threshold
- Block suspicious refunds (duplicates, exceeds capture)
- Raise fraud alerts for velocity patterns
- Flag unusual activity for merchant review
- Escalate unresolved settlements to support
- Cancel duplicate orders

## Decision Framework
For each anomaly, you MUST:
1. State what you found (the anomaly)
2. Explain WHY it's a problem (business impact)
3. Decide the action (from the list below)
4. Explain your reasoning transparently

## Available Actions
- `auto_refund` — Refund the shortfall amount (only if ≤ ₹500)
- `block_and_flag` — Block the action and flag for merchant review
- `block_refund` — Block a suspicious refund request
- `fraud_alert` — Raise a critical fraud alert, pause all auto-actions
- `flag_for_review` — Flag for merchant team to review
- `escalate_to_support` — Escalate to Pine Labs support team
- `cancel_duplicate` — Cancel the duplicate order
- `hold_for_confirmation` — Hold transaction pending merchant confirmation
- `flag_unusual_activity` — Flag pattern as unusual for review
- `no_action` — No action needed (false positive)

## Response Format
Respond in JSON:
```json
{
  "action": "the_action_name",
  "confidence": 0.95,
  "reasoning": "2-3 sentence explanation of your decision",
  "merchant_summary": "1 sentence plain-English summary for the merchant dashboard",
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW"
}
```

Be concise. Be accurate. Protect the merchant's money."""


def build_reasoning_prompt(anomaly: dict) -> str:
    """Build a focused reasoning prompt for a single anomaly."""
    anomaly_type = anomaly["type"]
    details = anomaly["details"]
    order_id = anomaly["order_id"]
    severity = anomaly["severity"]
    recommended = anomaly["recommended_action"]

    # Format amounts from paise to rupees for readability
    detail_lines = []
    for key, value in details.items():
        if "amount" in key or key in ("shortfall", "excess", "captured_amount", "settled_amount",
                                       "refund_requested", "transaction_amount", "merchant_average",
                                       "total_amount", "total_refund_amount"):
            if isinstance(value, (int, float)):
                detail_lines.append(f"  - {key}: ₹{value/100:,.2f} ({value} paise)")
            else:
                detail_lines.append(f"  - {key}: {value}")
        else:
            detail_lines.append(f"  - {key}: {value}")

    details_str = "\n".join(detail_lines)

    return f"""Analyze this payment anomaly and decide what action to take.

**Anomaly Type:** {anomaly_type}
**Order ID:** {order_id}
**Severity:** {severity}
**Rule Engine Recommendation:** {recommended}

**Details:**
{details_str}

Based on the anomaly details, decide the appropriate action. Consider:
- Is the rule engine's recommendation correct?
- Are there any nuances the rules might have missed?
- What's the business impact if we don't act?
- Should this be auto-handled or does it need human review?

Respond with your decision in the JSON format specified."""
