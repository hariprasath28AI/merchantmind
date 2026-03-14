"""Quick test script to verify Pine Labs API credentials work."""
import requests
import os
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("PINE_LABS_CLIENT_ID")
CLIENT_SECRET = os.getenv("PINE_LABS_CLIENT_SECRET")
BASE_URL = os.getenv("PINE_LABS_BASE_URL")

print(f"Base URL: {BASE_URL}")
print(f"Client ID: {CLIENT_ID[:8]}...")


def get_headers(access_token):
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Request-Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "Request-ID": str(uuid.uuid4()),
    }


# Step 1: Get OAuth token
print("\n--- Step 1: Fetching OAuth Token ---")
token_response = requests.post(
    f"{BASE_URL}/api/auth/v1/token",
    json={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
    },
)
print(f"Token Status: {token_response.status_code}")

if token_response.status_code == 200:
    token_data = token_response.json()
    access_token = token_data.get("access_token")
    expires_at = token_data.get("expires_at", "unknown")
    print(f"Access Token: {access_token[:30]}...")
    print(f"Expires At: {expires_at}")

    # Step 2: Test Settlements API
    print("\n--- Step 2: Testing Settlements API ---")
    settlements_response = requests.get(
        f"{BASE_URL}/api/settlements/v1/list",
        headers=get_headers(access_token),
    )
    print(f"Settlements Status: {settlements_response.status_code}")
    print(f"Settlements Response: {settlements_response.text[:500]}")

    # Step 3: Test Orders API (get order by ID - will likely 404 but confirms endpoint is reachable)
    print("\n--- Step 3: Testing Orders API ---")
    orders_response = requests.get(
        f"{BASE_URL}/api/pay/v1/orders/test-order-123",
        headers=get_headers(access_token),
    )
    print(f"Orders Status: {orders_response.status_code}")
    print(f"Orders Response: {orders_response.text[:500]}")

    # Step 4: Test Create Order (to confirm write access)
    print("\n--- Step 4: Testing Create Order API ---")
    create_order_response = requests.post(
        f"{BASE_URL}/api/pay/v1/orders",
        headers=get_headers(access_token),
        json={
            "merchant_order_reference": f"TEST_{uuid.uuid4().hex[:8]}",
            "order_amount": {"value": 10000, "currency": "INR"},
            "purchase_details": {
                "customer": {
                    "email_id": "test@example.com",
                    "first_name": "Test",
                    "last_name": "User",
                    "mobile_number": "9999999999",
                    "customer_id": "CUST_TEST_001",
                },
            },
        },
    )
    print(f"Create Order Status: {create_order_response.status_code}")
    print(f"Create Order Response: {create_order_response.text[:500]}")

    print("\n--- Summary ---")
    print(f"Auth:        {'PASS' if token_response.status_code == 200 else 'FAIL'}")
    print(f"Settlements: {'PASS' if settlements_response.status_code in [200, 204] else settlements_response.status_code}")
    print(f"Get Order:   {'PASS' if orders_response.status_code in [200, 404, 400] else orders_response.status_code}")
    print(f"Create Order: {'PASS' if create_order_response.status_code in [200, 201] else create_order_response.status_code}")
else:
    print(f"Token Response: {token_response.text[:500]}")
    print("\nFailed to get token. Cannot test other APIs.")
