"""Pine Labs REST client — settlements only (orders/refunds go through MCP)."""
import requests
import uuid
from datetime import datetime, timezone
from config import PINE_LABS_CLIENT_ID, PINE_LABS_CLIENT_SECRET, PINE_LABS_BASE_URL


class PineLabsClient:
    def __init__(self):
        self.base_url = PINE_LABS_BASE_URL
        self._token = None
        self._token_expires = None

    def _ensure_token(self):
        now = datetime.now(timezone.utc)
        if self._token and self._token_expires and now < self._token_expires:
            return
        resp = requests.post(
            f"{self.base_url}/api/auth/v1/token",
            json={
                "client_id": PINE_LABS_CLIENT_ID,
                "client_secret": PINE_LABS_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        if data.get("expires_at"):
            self._token_expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))

    def _headers(self):
        self._ensure_token()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Request-Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "Request-ID": str(uuid.uuid4()),
        }

    def get_settlements(self, start_date: str, end_date: str):
        """GET /api/settlements/v1/list — requires start_date/end_date (YYYY-MM-DD)."""
        resp = requests.get(
            f"{self.base_url}/api/settlements/v1/list",
            headers=self._headers(),
            params={"start_date": start_date, "end_date": end_date},
        )
        return resp.json()

    def get_settlement_by_utr(self, utr: str):
        """GET /api/settlements/v1/list?utr={utr}."""
        resp = requests.get(
            f"{self.base_url}/api/settlements/v1/list",
            headers=self._headers(),
            params={"utr": utr},
        )
        return resp.json()

    def get_order(self, order_id: str):
        """GET /api/pay/v1/orders/{order_id} — fallback if MCP is unavailable."""
        resp = requests.get(
            f"{self.base_url}/api/pay/v1/orders/{order_id}",
            headers=self._headers(),
        )
        return resp.json()

    def create_order(self, merchant_order_reference: str, amount_paise: int, customer: dict):
        """POST /api/pay/v1/orders — create a real order on sandbox."""
        resp = requests.post(
            f"{self.base_url}/api/pay/v1/orders",
            headers=self._headers(),
            json={
                "merchant_order_reference": merchant_order_reference,
                "order_amount": {"value": amount_paise, "currency": "INR"},
                "purchase_details": {"customer": customer},
            },
        )
        return resp.json()
