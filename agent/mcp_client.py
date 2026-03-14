"""Pine Labs MCP Client — connects to hosted MCP server for executing actions.

Falls back to REST API or simulation if MCP is unavailable.
"""
import logging
import requests
import uuid
from datetime import datetime, timezone
from config import PINE_LABS_CLIENT_ID, PINE_LABS_CLIENT_SECRET, PINE_LABS_BASE_URL

logger = logging.getLogger(__name__)

MCP_URL = "https://mcp.pinelabs.com/sse"
BUSINESS_NAME = "MerchantMind"


class PineLabsActionClient:
    """Executes payment actions via Pine Labs REST API with MCP-style interface.

    Tries REST API first. If that fails, returns a simulated result
    so the demo flow continues.
    """

    def __init__(self):
        self.base_url = PINE_LABS_BASE_URL
        self._token = None

    def _ensure_token(self):
        if self._token:
            return
        try:
            resp = requests.post(
                f"{self.base_url}/api/auth/v1/token",
                json={
                    "client_id": PINE_LABS_CLIENT_ID,
                    "client_secret": PINE_LABS_CLIENT_SECRET,
                    "grant_type": "client_credentials",
                },
                timeout=10,
            )
            resp.raise_for_status()
            self._token = resp.json()["access_token"]
        except Exception as e:
            logger.warning(f"Token fetch failed: {e}")

    def _headers(self):
        self._ensure_token()
        return {
            "Authorization": f"Bearer {self._token}" if self._token else "",
            "Content-Type": "application/json",
            "Request-Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "Request-ID": str(uuid.uuid4()),
        }

    def create_refund(self, order_id: str, amount_paise: int, reason: str = "settlement_shortfall") -> dict:
        """Create a refund for the given order.

        Tries Pine Labs REST API: POST /api/pay/v1/refunds/{order_id}
        Falls back to simulated if API fails.
        """
        logger.info(f"Executing refund: order={order_id}, amount={amount_paise} paise, reason={reason}")

        try:
            self._ensure_token()
            if self._token:
                # Fetch the order to get merchant_order_reference (required by Pine Labs)
                mor = None
                try:
                    order_resp = requests.get(
                        f"{self.base_url}/api/pay/v1/orders/{order_id}",
                        headers=self._headers(),
                        timeout=10,
                    )
                    if order_resp.status_code == 200:
                        mor = order_resp.json().get("data", {}).get("merchant_order_reference")
                except Exception as e:
                    logger.warning(f"Failed to fetch MOR for {order_id}: {e}")

                payload = {
                    "merchant_refund_reference": f"MR_{uuid.uuid4().hex[:8]}",
                    "refund_amount": amount_paise,
                }
                if mor:
                    payload["merchant_order_reference"] = mor

                resp = requests.post(
                    f"{self.base_url}/api/pay/v1/refunds/{order_id}",
                    headers=self._headers(),
                    json=payload,
                    timeout=15,
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    refund_order = data.get("data", {})
                    return {
                        "status": "executed",
                        "method": "pine_labs_api",
                        "refund_id": refund_order.get("order_id", f"REF_{uuid.uuid4().hex[:8]}"),
                        "refund_status": refund_order.get("status", "UNKNOWN"),
                        "amount": amount_paise,
                        "order_id": order_id,
                        "approval_code": refund_order.get("payments", [{}])[0].get("acquirer_data", {}).get("approval_code"),
                        "response": data,
                    }
                else:
                    logger.warning(f"Refund API returned {resp.status_code}: {resp.text[:200]}")
                    return {
                        "status": "simulated",
                        "method": "pine_labs_api_attempted",
                        "refund_id": f"SIM_REF_{uuid.uuid4().hex[:8]}",
                        "amount": amount_paise,
                        "order_id": order_id,
                        "api_status_code": resp.status_code,
                        "note": f"Pine Labs API called (real order) — {resp.status_code}: {resp.text[:100]}",
                    }
        except Exception as e:
            logger.warning(f"Refund API call failed: {e}")

        # Fallback: simulated execution (mock order IDs)
        return {
            "status": "simulated",
            "method": "simulated",
            "refund_id": f"SIM_REF_{uuid.uuid4().hex[:8]}",
            "amount": amount_paise,
            "order_id": order_id,
            "note": "Simulated — mock order ID not on Pine Labs sandbox",
        }

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a duplicate order.

        Tries Pine Labs REST API: PUT /api/pay/v1/orders/{order_id}/cancel
        Falls back to simulated.
        """
        logger.info(f"Executing cancel: order={order_id}")

        try:
            self._ensure_token()
            if self._token:
                resp = requests.put(
                    f"{self.base_url}/api/pay/v1/orders/{order_id}/cancel",
                    headers=self._headers(),
                    timeout=15,
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    return {
                        "status": "executed",
                        "method": "pine_labs_api",
                        "order_id": order_id,
                        "response": data,
                    }
                else:
                    logger.warning(f"Cancel API returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Cancel API call failed: {e}")

        return {
            "status": "simulated",
            "method": "simulated",
            "order_id": order_id,
            "note": "Simulated — order is mock data, not on Pine Labs sandbox",
        }

    def get_order(self, order_id: str) -> dict:
        """Get order details for verification."""
        logger.info(f"Fetching order: {order_id}")

        try:
            self._ensure_token()
            if self._token:
                resp = requests.get(
                    f"{self.base_url}/api/pay/v1/orders/{order_id}",
                    headers=self._headers(),
                    timeout=10,
                )
                if resp.status_code == 200:
                    return {"status": "fetched", "data": resp.json()}
        except Exception as e:
            logger.warning(f"Get order failed: {e}")

        return {"status": "unavailable", "order_id": order_id}

    def verify_refund(self, order_id: str) -> dict:
        """Verify a refund was processed."""
        logger.info(f"Verifying refund for: {order_id}")
        # In sandbox, we check order status
        return self.get_order(order_id)

    def get_settlements(self, start_date: str, end_date: str, page: int = 1, per_page: int = 10) -> dict:
        """Fetch settlements from Pine Labs Settlement API.

        GET /api/settlements/v1/list
        Date format: '2026-03-14T00:00:00' (no Z suffix)
        Max date range: 60 days. Max per_page: 10.
        """
        logger.info(f"Fetching settlements: {start_date} to {end_date}, page={page}")

        try:
            self._ensure_token()
            if self._token:
                resp = requests.get(
                    f"{self.base_url}/api/settlements/v1/list",
                    headers=self._headers(),
                    params={
                        "start_date": start_date,
                        "end_date": end_date,
                        "page": str(page),
                        "per_page": str(per_page),
                    },
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "status": "fetched",
                        "data": data.get("data", []),
                        "total_count": data.get("total_settlement_count", 0),
                        "total_amount": data.get("total_settlement_amount", 0),
                    }
                else:
                    logger.warning(f"Settlement API returned {resp.status_code}: {resp.text[:200]}")
                    return {"status": "error", "code": resp.status_code, "message": resp.text[:200]}
        except Exception as e:
            logger.warning(f"Settlement API call failed: {e}")

        return {"status": "unavailable"}
