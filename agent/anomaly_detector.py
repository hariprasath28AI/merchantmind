"""Rule-based anomaly detection engine — fast pre-filter before LLM reasoning.

Scans transactions + settlements and flags anomalies for the agent to reason about.
"""
from datetime import datetime, timedelta
from collections import defaultdict
from config import (
    AUTO_REFUND_THRESHOLD_PAISE,
    FRAUD_VELOCITY_WINDOW_MINUTES,
    FRAUD_VELOCITY_MAX_REFUNDS,
    HIGH_VALUE_MULTIPLIER,
    MIDNIGHT_HOUR_START,
    MIDNIGHT_HOUR_END,
    MIDNIGHT_BURST_THRESHOLD,
)


def detect_all_anomalies(transactions: list, settlements: list) -> list:
    """Run all anomaly checks and return list of detected anomalies."""
    # Build lookup maps
    settlement_map = {s["order_id"]: s for s in settlements}
    txn_map = {t["order_id"]: t for t in transactions}

    anomalies = []

    # Per-transaction checks
    for txn in transactions:
        order_id = txn["order_id"]
        settlement = settlement_map.get(order_id)

        # 1. Settlement shortfall
        if settlement:
            captured = txn["captured_amount"]["value"]
            settled = settlement["settled_amount"]["value"]
            if settled < captured and settled > 0:
                anomalies.append({
                    "type": "settlement_shortfall",
                    "severity": "HIGH" if (captured - settled) > AUTO_REFUND_THRESHOLD_PAISE else "MEDIUM",
                    "order_id": order_id,
                    "details": {
                        "captured_amount": captured,
                        "settled_amount": settled,
                        "shortfall": captured - settled,
                        "payment_method": txn.get("payment_method"),
                    },
                    "recommended_action": "auto_refund" if (captured - settled) <= AUTO_REFUND_THRESHOLD_PAISE else "flag_for_review",
                    "transaction": txn,
                    "settlement": settlement,
                })

        # 2. Duplicate refund
        if txn.get("has_existing_refund") and txn.get("refund_requested"):
            existing = txn.get("existing_refund", {})
            anomalies.append({
                "type": "duplicate_refund",
                "severity": "HIGH",
                "order_id": order_id,
                "details": {
                    "existing_refund_id": existing.get("refund_id"),
                    "existing_refund_status": existing.get("status"),
                    "existing_refund_amount": existing.get("amount", {}).get("value"),
                    "new_refund_amount": txn.get("refund_requested_amount", {}).get("value"),
                },
                "recommended_action": "block_and_flag",
                "transaction": txn,
            })

        # 4. Over-settlement (skip PARTIALLY_CAPTURED — handled by partial_capture_mismatch)
        if settlement and txn.get("status") != "PARTIALLY_CAPTURED":
            captured = txn["captured_amount"]["value"]
            settled = settlement["settled_amount"]["value"]
            if settled > captured:
                anomalies.append({
                    "type": "over_settlement",
                    "severity": "MEDIUM",
                    "order_id": order_id,
                    "details": {
                        "captured_amount": captured,
                        "settled_amount": settled,
                        "excess": settled - captured,
                    },
                    "recommended_action": "flag_for_review",
                    "transaction": txn,
                    "settlement": settlement,
                })

        # 5. Late settlement
        if settlement and settlement.get("settlement_status") == "PENDING":
            created = datetime.strptime(txn["created_at"], "%Y-%m-%dT%H:%M:%S.000Z")
            age_days = (datetime.utcnow() - created).days
            if age_days >= 3:
                anomalies.append({
                    "type": "late_settlement",
                    "severity": "HIGH",
                    "order_id": order_id,
                    "details": {
                        "captured_amount": txn["captured_amount"]["value"],
                        "days_pending": age_days,
                        "created_at": txn["created_at"],
                    },
                    "recommended_action": "escalate_to_support",
                    "transaction": txn,
                    "settlement": settlement,
                })

        # 6. Refund exceeds capture
        if txn.get("refund_requested"):
            refund_amt = txn.get("refund_requested_amount", {}).get("value", 0)
            captured = txn["captured_amount"]["value"]
            if refund_amt > captured:
                anomalies.append({
                    "type": "refund_exceeds_capture",
                    "severity": "HIGH",
                    "order_id": order_id,
                    "details": {
                        "captured_amount": captured,
                        "refund_requested": refund_amt,
                        "excess": refund_amt - captured,
                    },
                    "recommended_action": "block_refund",
                    "transaction": txn,
                })

        # 9. Partial capture mismatch
        if txn.get("status") == "PARTIALLY_CAPTURED" and settlement:
            captured = txn["captured_amount"]["value"]
            settled = settlement["settled_amount"]["value"]
            if settled > captured:
                anomalies.append({
                    "type": "partial_capture_mismatch",
                    "severity": "MEDIUM",
                    "order_id": order_id,
                    "details": {
                        "order_amount": txn["order_amount"]["value"],
                        "captured_amount": captured,
                        "settled_amount": settled,
                    },
                    "recommended_action": "flag_over_settlement",
                    "transaction": txn,
                    "settlement": settlement,
                })

    # --- Cross-transaction checks ---

    # 3. Refund velocity fraud
    card_refunds = defaultdict(list)
    for txn in transactions:
        if txn.get("refund_requested") and txn.get("card_fingerprint"):
            ts = datetime.strptime(txn["created_at"], "%Y-%m-%dT%H:%M:%S.000Z")
            card_refunds[txn["card_fingerprint"]].append((ts, txn))

    for card_fp, refund_list in card_refunds.items():
        refund_list.sort(key=lambda x: x[0])
        window = timedelta(minutes=FRAUD_VELOCITY_WINDOW_MINUTES)
        for i, (ts, _) in enumerate(refund_list):
            window_txns = [(t, txn) for t, txn in refund_list if ts <= t <= ts + window]
            if len(window_txns) > FRAUD_VELOCITY_MAX_REFUNDS:
                total_amount = sum(
                    txn.get("refund_requested_amount", {}).get("value", 0)
                    for _, txn in window_txns
                )
                anomalies.append({
                    "type": "refund_velocity_fraud",
                    "severity": "CRITICAL",
                    "order_id": window_txns[0][1]["order_id"],
                    "details": {
                        "card_fingerprint": card_fp,
                        "refund_count": len(window_txns),
                        "total_refund_amount": total_amount,
                        "window_minutes": FRAUD_VELOCITY_WINDOW_MINUTES,
                        "order_ids": [txn["order_id"] for _, txn in window_txns],
                    },
                    "recommended_action": "fraud_alert",
                    "transactions": [txn for _, txn in window_txns],
                })
                break  # one alert per card

    # 7. Duplicate orders (same merchant_order_reference)
    mor_map = defaultdict(list)
    for txn in transactions:
        mor_map[txn["merchant_order_reference"]].append(txn)

    for mor, txn_list in mor_map.items():
        if len(txn_list) > 1:
            anomalies.append({
                "type": "duplicate_order",
                "severity": "HIGH",
                "order_id": txn_list[0]["order_id"],
                "details": {
                    "merchant_order_reference": mor,
                    "duplicate_order_ids": [t["order_id"] for t in txn_list],
                    "amounts": [t["captured_amount"]["value"] for t in txn_list],
                    "customer_id": txn_list[0]["customer"]["customer_id"],
                },
                "recommended_action": "cancel_duplicate",
                "transactions": txn_list,
            })

    # 8. High-value outlier
    amounts = [t["captured_amount"]["value"] for t in transactions]
    avg_amount = sum(amounts) / len(amounts) if amounts else 0
    for txn in transactions:
        if txn["captured_amount"]["value"] > avg_amount * HIGH_VALUE_MULTIPLIER:
            anomalies.append({
                "type": "high_value_outlier",
                "severity": "MEDIUM",
                "order_id": txn["order_id"],
                "details": {
                    "transaction_amount": txn["captured_amount"]["value"],
                    "merchant_average": round(avg_amount),
                    "multiplier": round(txn["captured_amount"]["value"] / avg_amount, 1),
                    "payment_method": txn.get("payment_method"),
                },
                "recommended_action": "hold_for_confirmation",
                "transaction": txn,
            })

    # 10. Midnight burst
    customer_midnight = defaultdict(list)
    for txn in transactions:
        ts = datetime.strptime(txn["created_at"], "%Y-%m-%dT%H:%M:%S.000Z")
        if MIDNIGHT_HOUR_START <= ts.hour < MIDNIGHT_HOUR_END:
            customer_midnight[txn["customer"]["customer_id"]].append(txn)

    for cust_id, txn_list in customer_midnight.items():
        if len(txn_list) >= MIDNIGHT_BURST_THRESHOLD:
            total_amount = sum(t["captured_amount"]["value"] for t in txn_list)
            anomalies.append({
                "type": "midnight_burst",
                "severity": "MEDIUM",
                "order_id": txn_list[0]["order_id"],
                "details": {
                    "customer_id": cust_id,
                    "transaction_count": len(txn_list),
                    "total_amount": total_amount,
                    "time_range": f"{txn_list[0]['created_at']} → {txn_list[-1]['created_at']}",
                    "order_ids": [t["order_id"] for t in txn_list],
                },
                "recommended_action": "flag_unusual_activity",
                "transactions": txn_list,
            })

    # Deduplicate (over_settlement and partial_capture_mismatch can overlap)
    seen = set()
    unique_anomalies = []
    for a in anomalies:
        key = (a["type"], a["order_id"])
        if key not in seen:
            seen.add(key)
            unique_anomalies.append(a)

    return unique_anomalies
