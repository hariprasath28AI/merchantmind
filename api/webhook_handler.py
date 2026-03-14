"""Pine Labs webhook handler — receives real-time payment events."""
from fastapi import APIRouter, Request, BackgroundTasks
import hmac
import hashlib
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Will be set by main.py when agent is initialized
agent_callback = None


def set_agent_callback(callback):
    global agent_callback
    agent_callback = callback


@router.post("/webhooks/pine-labs")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    event_type = payload.get("event_type", "unknown")

    logger.info(f"Webhook received: {event_type}")

    # In production, verify HMAC-SHA256 signature
    # signature = request.headers.get("X-Pine-Signature")
    # if not _verify_signature(payload, signature):
    #     return {"status": "invalid_signature"}

    supported_events = [
        "payment.captured",
        "payment.failed",
        "refund.created",
        "order.cancelled",
    ]

    if event_type in supported_events and agent_callback:
        background_tasks.add_task(
            agent_callback,
            event_type=event_type,
            event_data=payload.get("data", {}),
        )

    return {
        "status": "received",
        "event_type": event_type,
        "order_id": payload.get("data", {}).get("order_id", ""),
    }


def _verify_signature(payload: dict, signature: str, secret: str = "") -> bool:
    """Verify Pine Labs HMAC-SHA256 webhook signature."""
    if not signature or not secret:
        return True  # Skip in dev/sandbox
    expected = hmac.new(
        secret.encode(),
        json.dumps(payload, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
