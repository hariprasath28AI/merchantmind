"""Generate 500 mock transactions + settlements with 10 planted anomalies."""
import json
import random
from datetime import datetime, timedelta

random.seed(42)

MERCHANT_ID = "121478"
BASE_TIME = datetime(2026, 3, 14, 6, 0, 0)  # 6 AM IST start

# Real order IDs created on Pine Labs sandbox (MID 121478) via Payment Links
REAL_ORDER_1 = "v1-260314080339-aa-jvGXHr"  # ₹1,500 — settlement shortfall demo
REAL_ORDER_2 = "v1-260314080704-aa-HiRhlJ"  # ₹750  — refund test / duplicate refund demo
REAL_ORDER_3 = "v1-260314080824-aa-v9WtQz"  # ₹2,000 — over-settlement test

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna",
    "Ishaan", "Shaurya", "Atharva", "Advik", "Pranav", "Advaith", "Aarush",
    "Ananya", "Saanvi", "Aanya", "Aadhya", "Isha", "Diya", "Priya", "Meera",
    "Kavya", "Riya", "Neha", "Pooja", "Shreya", "Tanvi", "Nisha",
]
LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Gupta", "Singh", "Kumar", "Reddy", "Nair",
    "Iyer", "Joshi", "Mehta", "Shah", "Rao", "Pillai", "Menon",
    "Desai", "Bhat", "Kulkarni", "Chopra", "Malhotra",
]
PAYMENT_METHODS = ["UPI"] * 40 + ["CARD"] * 30 + ["NETBANKING"] * 20 + ["WALLET"] * 10


def make_customer(idx):
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return {
        "customer_id": f"CUST_{idx:04d}",
        "first_name": first,
        "last_name": last,
        "email_id": f"{first.lower()}.{last.lower()}@example.com",
        "mobile_number": f"9{random.randint(100000000, 999999999)}",
        "country_code": "91",
    }


def make_order(idx, timestamp, amount_paise, payment_method, status="CAPTURED", card_fp=None):
    order_id = f"v1-260314-ORD-{idx:04d}"
    customer = make_customer(idx)
    return {
        "order_id": order_id,
        "merchant_order_reference": f"MOR_{idx:04d}",
        "type": "CHARGE",
        "status": status,
        "merchant_id": MERCHANT_ID,
        "order_amount": {"value": amount_paise, "currency": "INR"},
        "captured_amount": {"value": amount_paise, "currency": "INR"},
        "payment_method": payment_method,
        "card_fingerprint": card_fp or f"CARD_{random.randint(100, 999)}",
        "customer": customer,
        "created_at": timestamp.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "updated_at": (timestamp + timedelta(seconds=random.randint(1, 10))).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        ),
    }


def make_settlement(order, settled_amount_paise=None, settlement_status="SETTLED", settlement_date=None):
    amt = settled_amount_paise if settled_amount_paise is not None else order["captured_amount"]["value"]
    fee = int(amt * 0.02)  # 2% processing fee
    sdate = settlement_date or (
        datetime.strptime(order["created_at"], "%Y-%m-%dT%H:%M:%S.000Z") + timedelta(hours=random.randint(4, 24))
    )
    return {
        "order_id": order["order_id"],
        "merchant_order_reference": order["merchant_order_reference"],
        "utr": f"UTR_20260314_{order['order_id'].split('-')[-1]}",
        "settled_amount": {"value": amt, "currency": "INR"},
        "captured_amount": {"value": order["captured_amount"]["value"], "currency": "INR"},
        "settlement_status": settlement_status,
        "settlement_date": sdate.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "fees": {"value": fee, "currency": "INR"},
        "payment_method": order["payment_method"],
    }


def generate():
    transactions = []
    settlements = []
    anomalies = []

    # --- Generate 500 normal transactions ---
    for i in range(500):
        ts = BASE_TIME + timedelta(minutes=i * 1.2, seconds=random.randint(0, 30))
        amount = random.randint(10000, 500000)  # ₹100 to ₹5,000
        pm = random.choice(PAYMENT_METHODS)
        order = make_order(i, ts, amount, pm)
        settlement = make_settlement(order)
        transactions.append(order)
        settlements.append(settlement)

    # --- ANOMALY 1: Settlement shortfall (index 50) ---
    # Uses REAL Pine Labs sandbox order ID for live API demo
    idx = 50
    transactions[idx]["order_id"] = REAL_ORDER_1
    transactions[idx]["merchant_order_reference"] = "MOR_RECON_TEST_001"
    transactions[idx]["captured_amount"] = {"value": 150000, "currency": "INR"}
    transactions[idx]["order_amount"] = {"value": 150000, "currency": "INR"}
    transactions[idx]["payment_method"] = "UPI"
    settlements[idx]["order_id"] = REAL_ORDER_1
    settlements[idx]["merchant_order_reference"] = "MOR_RECON_TEST_001"
    settlements[idx]["settled_amount"] = {"value": 130000, "currency": "INR"}
    settlements[idx]["captured_amount"] = {"value": 150000, "currency": "INR"}
    settlements[idx]["settlement_status"] = "SETTLED"
    anomalies.append({
        "index": idx,
        "order_id": REAL_ORDER_1,
        "type": "settlement_shortfall",
        "description": "Captured ₹1,500 but settled ₹1,300 — ₹200 gap (REAL order on sandbox)",
        "expected_action": "auto_refund",
        "severity": "MEDIUM",
    })

    # --- ANOMALY 2: Duplicate refund (index 100) ---
    # Uses REAL Pine Labs sandbox order ID for live API demo
    idx = 100
    transactions[idx]["order_id"] = REAL_ORDER_2
    transactions[idx]["merchant_order_reference"] = "MOR_RECON_TEST_002"
    transactions[idx]["captured_amount"] = {"value": 75000, "currency": "INR"}
    transactions[idx]["order_amount"] = {"value": 75000, "currency": "INR"}
    transactions[idx]["has_existing_refund"] = True
    transactions[idx]["existing_refund"] = {
        "refund_id": "REF_789",
        "amount": {"value": 75000, "currency": "INR"},
        "status": "PROCESSED",
        "created_at": "2026-03-14T10:30:00.000Z",
    }
    transactions[idx]["refund_requested"] = True
    transactions[idx]["refund_requested_amount"] = {"value": 75000, "currency": "INR"}
    # FIX: Align settlement amounts to prevent spurious over/under-settlement anomalies
    settlements[idx]["order_id"] = REAL_ORDER_2
    settlements[idx]["merchant_order_reference"] = "MOR_RECON_TEST_002"
    settlements[idx]["settled_amount"] = {"value": 75000, "currency": "INR"}
    settlements[idx]["captured_amount"] = {"value": 75000, "currency": "INR"}
    settlements[idx]["settlement_status"] = "SETTLED"
    anomalies.append({
        "index": idx,
        "order_id": REAL_ORDER_2,
        "type": "duplicate_refund",
        "description": "Refund REF_789 already processed for ₹750, second refund request incoming (REAL order on sandbox)",
        "expected_action": "block_and_flag",
        "severity": "HIGH",
    })

    # --- ANOMALY 3: Refund velocity fraud (index 200-204) ---
    fraud_card = "CARD_FRAUD_001"
    fraud_time = BASE_TIME + timedelta(hours=6)
    for j in range(5):
        idx = 200 + j
        transactions[idx]["order_id"] = f"v1-260314-DEMO-003-{j}"
        transactions[idx]["card_fingerprint"] = fraud_card
        transactions[idx]["payment_method"] = "CARD"
        transactions[idx]["captured_amount"] = {"value": 50000, "currency": "INR"}
        transactions[idx]["order_amount"] = {"value": 50000, "currency": "INR"}
        transactions[idx]["refund_requested"] = True
        transactions[idx]["refund_requested_amount"] = {"value": 50000, "currency": "INR"}
        transactions[idx]["created_at"] = (fraud_time + timedelta(minutes=j * 10)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        # FIX: Align settlement to prevent spurious shortfall/excess anomalies
        settlements[idx]["order_id"] = f"v1-260314-DEMO-003-{j}"
        settlements[idx]["settled_amount"] = {"value": 50000, "currency": "INR"}
        settlements[idx]["captured_amount"] = {"value": 50000, "currency": "INR"}
    anomalies.append({
        "index": "200-204",
        "order_ids": [f"v1-260314-DEMO-003-{j}" for j in range(5)],
        "type": "refund_velocity_fraud",
        "description": "5 refunds to CARD_FRAUD_001 in 60 min totalling ₹2,500",
        "expected_action": "fraud_alert",
        "severity": "CRITICAL",
    })

    # --- ANOMALY 4: Over-settlement (index 120) ---
    # Uses REAL Pine Labs sandbox order ID for live API demo
    idx = 120
    transactions[idx]["order_id"] = REAL_ORDER_3
    transactions[idx]["captured_amount"] = {"value": 200000, "currency": "INR"}
    transactions[idx]["order_amount"] = {"value": 200000, "currency": "INR"}
    settlements[idx]["order_id"] = REAL_ORDER_3
    settlements[idx]["settled_amount"] = {"value": 250000, "currency": "INR"}
    settlements[idx]["captured_amount"] = {"value": 200000, "currency": "INR"}
    anomalies.append({
        "index": idx,
        "order_id": REAL_ORDER_3,
        "type": "over_settlement",
        "description": "Captured ₹2,000 but settled ₹2,500 — ₹500 extra credited (REAL order on sandbox)",
        "expected_action": "flag_for_review",
        "severity": "MEDIUM",
    })

    # --- ANOMALY 5: Late settlement (index 160) ---
    idx = 160
    transactions[idx]["order_id"] = "v1-260314-DEMO-005"
    transactions[idx]["captured_amount"] = {"value": 250000, "currency": "INR"}
    transactions[idx]["order_amount"] = {"value": 250000, "currency": "INR"}
    transactions[idx]["created_at"] = (BASE_TIME - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    settlements[idx]["order_id"] = "v1-260314-DEMO-005"
    settlements[idx]["settlement_status"] = "PENDING"
    settlements[idx]["settled_amount"] = {"value": 0, "currency": "INR"}
    settlements[idx]["captured_amount"] = {"value": 250000, "currency": "INR"}
    settlements[idx]["settlement_date"] = None
    anomalies.append({
        "index": idx,
        "order_id": "v1-260314-DEMO-005",
        "type": "late_settlement",
        "description": "Payment captured 5 days ago (₹2,500), still no settlement",
        "expected_action": "escalate_to_support",
        "severity": "HIGH",
    })

    # --- ANOMALY 6: Refund exceeds capture (index 250) ---
    idx = 250
    transactions[idx]["order_id"] = "v1-260314-DEMO-006"
    transactions[idx]["captured_amount"] = {"value": 200000, "currency": "INR"}
    transactions[idx]["order_amount"] = {"value": 200000, "currency": "INR"}
    transactions[idx]["refund_requested"] = True
    transactions[idx]["refund_requested_amount"] = {"value": 300000, "currency": "INR"}
    # FIX: Align settlement to prevent spurious shortfall/excess anomalies
    settlements[idx]["order_id"] = "v1-260314-DEMO-006"
    settlements[idx]["settled_amount"] = {"value": 200000, "currency": "INR"}
    settlements[idx]["captured_amount"] = {"value": 200000, "currency": "INR"}
    settlements[idx]["settlement_status"] = "SETTLED"
    anomalies.append({
        "index": idx,
        "order_id": "v1-260314-DEMO-006",
        "type": "refund_exceeds_capture",
        "description": "Refund of ₹3,000 requested on ₹2,000 capture",
        "expected_action": "block_refund",
        "severity": "HIGH",
    })

    # --- ANOMALY 7: Duplicate order (index 300, 301) ---
    dup_mor = "MOR_DUP_LAPTOP"
    dup_customer = make_customer(9999)
    for j, idx in enumerate([300, 301]):
        transactions[idx]["order_id"] = f"v1-260314-DEMO-007-{j}"
        transactions[idx]["merchant_order_reference"] = dup_mor
        transactions[idx]["captured_amount"] = {"value": 450000, "currency": "INR"}
        transactions[idx]["order_amount"] = {"value": 450000, "currency": "INR"}
        transactions[idx]["customer"] = dup_customer
        transactions[idx]["payment_method"] = "CARD"
        transactions[idx]["created_at"] = (BASE_TIME + timedelta(hours=7, minutes=j * 2)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        # FIX: Align settlement to prevent spurious shortfall anomalies
        settlements[idx]["order_id"] = f"v1-260314-DEMO-007-{j}"
        settlements[idx]["merchant_order_reference"] = dup_mor
        settlements[idx]["settled_amount"] = {"value": 450000, "currency": "INR"}
        settlements[idx]["captured_amount"] = {"value": 450000, "currency": "INR"}
    anomalies.append({
        "index": "300-301",
        "order_ids": ["v1-260314-DEMO-007-0", "v1-260314-DEMO-007-1"],
        "type": "duplicate_order",
        "description": "Same merchant_order_reference MOR_DUP_LAPTOP, two charges of ₹4,500",
        "expected_action": "cancel_duplicate",
        "severity": "HIGH",
    })

    # --- ANOMALY 8: High-value outlier (index 350) ---
    idx = 350
    transactions[idx]["order_id"] = "v1-260314-DEMO-008"
    transactions[idx]["captured_amount"] = {"value": 4900000, "currency": "INR"}  # ₹49,000
    transactions[idx]["order_amount"] = {"value": 4900000, "currency": "INR"}
    transactions[idx]["payment_method"] = "CARD"
    settlements[idx]["order_id"] = "v1-260314-DEMO-008"
    settlements[idx]["settled_amount"] = {"value": 4900000, "currency": "INR"}
    settlements[idx]["captured_amount"] = {"value": 4900000, "currency": "INR"}
    anomalies.append({
        "index": idx,
        "order_id": "v1-260314-DEMO-008",
        "type": "high_value_outlier",
        "description": "Single txn ₹49,000 — merchant avg is ~₹1,500. 32x standard deviation",
        "expected_action": "hold_for_confirmation",
        "severity": "MEDIUM",
    })

    # --- ANOMALY 9: Partial capture mismatch (index 400) ---
    idx = 400
    transactions[idx]["order_id"] = "v1-260314-DEMO-009"
    transactions[idx]["order_amount"] = {"value": 200000, "currency": "INR"}
    transactions[idx]["captured_amount"] = {"value": 150000, "currency": "INR"}  # partial capture
    transactions[idx]["status"] = "PARTIALLY_CAPTURED"
    settlements[idx]["order_id"] = "v1-260314-DEMO-009"
    settlements[idx]["settled_amount"] = {"value": 200000, "currency": "INR"}  # settled full amount!
    settlements[idx]["captured_amount"] = {"value": 150000, "currency": "INR"}
    anomalies.append({
        "index": idx,
        "order_id": "v1-260314-DEMO-009",
        "type": "partial_capture_mismatch",
        "description": "Order ₹2,000, partial capture ₹1,500, but settled full ₹2,000",
        "expected_action": "flag_over_settlement",
        "severity": "MEDIUM",
    })

    # --- ANOMALY 10: Midnight burst (index 450-457) ---
    midnight_customer_id = "CUST_MIDNIGHT_001"
    midnight_customer = {
        "customer_id": midnight_customer_id,
        "first_name": "Rajesh",
        "last_name": "Kumar",
        "email_id": "rajesh.kumar@example.com",
        "mobile_number": "9876543210",
        "country_code": "91",
    }
    midnight_time = datetime(2026, 3, 14, 2, 0, 0)  # 2 AM
    for j in range(8):
        idx = 450 + j
        transactions[idx]["order_id"] = f"v1-260314-DEMO-010-{j}"
        transactions[idx]["customer"] = midnight_customer
        transactions[idx]["captured_amount"] = {"value": random.randint(20000, 80000), "currency": "INR"}
        transactions[idx]["order_amount"] = transactions[idx]["captured_amount"].copy()
        transactions[idx]["payment_method"] = "UPI"
        transactions[idx]["created_at"] = (midnight_time + timedelta(minutes=j * 7)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        settlements[idx]["order_id"] = f"v1-260314-DEMO-010-{j}"
        settlements[idx]["settled_amount"] = transactions[idx]["captured_amount"].copy()
        settlements[idx]["captured_amount"] = transactions[idx]["captured_amount"].copy()
    anomalies.append({
        "index": "450-457",
        "order_ids": [f"v1-260314-DEMO-010-{j}" for j in range(8)],
        "type": "midnight_burst",
        "description": "8 UPI transactions from CUST_MIDNIGHT_001 between 2:00-2:56 AM",
        "expected_action": "flag_unusual_activity",
        "severity": "MEDIUM",
    })

    return transactions, settlements, anomalies


if __name__ == "__main__":
    transactions, settlements, anomalies = generate()

    with open("data/mock_transactions.json", "w") as f:
        json.dump(transactions, f, indent=2)

    with open("data/mock_settlements.json", "w") as f:
        json.dump(settlements, f, indent=2)

    with open("data/anomalies_manifest.json", "w") as f:
        json.dump(anomalies, f, indent=2)

    print(f"Generated {len(transactions)} transactions")
    print(f"Generated {len(settlements)} settlements")
    print(f"Planted {len(anomalies)} anomalies:")
    for a in anomalies:
        print(f"  [{a['severity']}] {a['type']}: {a['description']}")
