"""FastAPI backend for MerchantMind — API + WebSocket for real-time agent streaming."""
import json
import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

from api.webhook_handler import router as webhook_router, set_agent_callback
from agent.graph import build_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MerchantMind", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)

# WebSocket connections for live dashboard
connected_clients: list[WebSocket] = []

# Store latest scan results
latest_results = {"results": [], "summary": {}, "log_entries": [], "scan_time": None}


async def broadcast(message: dict):
    """Send message to all connected WebSocket clients."""
    dead = []
    for ws in connected_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)


@app.websocket("/ws/agent-log")
async def agent_log_ws(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    logger.info(f"Dashboard connected. Total clients: {len(connected_clients)}")

    # Send latest results if available
    if latest_results["scan_time"]:
        await websocket.send_json({"type": "full_state", "data": latest_results})

    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        logger.info(f"Dashboard disconnected. Total clients: {len(connected_clients)}")


@app.post("/api/scan")
async def trigger_scan():
    """Trigger a full transaction scan — the main demo endpoint."""
    agent = build_agent()

    initial_state = {
        "transactions": [],
        "settlements": [],
        "anomalies": [],
        "current_anomaly_index": 0,
        "results": [],
        "log_entries": [],
    }

    await broadcast({"type": "scan_started", "data": {"time": _now()}})

    # Run the agent
    final_state = None
    async for state in agent.astream(initial_state):
        # state is a dict with node name as key
        for node_name, node_state in state.items():
            log_entries = node_state.get("log_entries", [])
            if log_entries:
                latest_entry = log_entries[-1]
                latest_entry["time"] = _now()
                await broadcast({"type": "log_entry", "data": latest_entry})

            # Stream individual results as they come
            results = node_state.get("results", [])
            if results and (not final_state or len(results) > len(final_state.get("results", []))):
                new_result = results[-1]
                await broadcast({"type": "anomaly_result", "data": new_result})

            final_state = node_state

    # Store and broadcast final summary
    # Summary may be nested under "summarize" node output or at top level
    summary = final_state.get("summary", {})
    if not summary:
        # Compute summary from results directly
        results_list = final_state.get("results", [])
        auto_fixed = sum(1 for r in results_list if r["decision"]["action"] in ("auto_refund", "cancel_duplicate"))
        flagged = sum(1 for r in results_list if r["decision"]["action"] in ("block_and_flag", "block_refund", "fraud_alert"))
        review = len(results_list) - auto_fixed - flagged
        summary = {
            "total_anomalies": len(results_list),
            "auto_fixed": auto_fixed,
            "flagged": flagged,
            "pending_review": review,
            "summary_text": f"Found {len(results_list)} issues. Fixed {auto_fixed} automatically. {flagged} flagged as critical. {review} need your review.",
        }
    latest_results.update({
        "results": final_state.get("results", []),
        "summary": summary,
        "log_entries": final_state.get("log_entries", []),
        "scan_time": _now(),
    })

    await broadcast({"type": "scan_complete", "data": latest_results})

    return {
        "status": "complete",
        "summary": summary,
        "anomaly_count": len(final_state.get("results", [])),
    }


@app.get("/api/anomalies")
async def get_anomalies():
    """Get latest scan results."""
    return latest_results


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "MerchantMind", "time": _now()}


@app.get("/api/settlements")
async def get_settlements(days: int = 30):
    """Pull real settlement data from Pine Labs Settlement API."""
    from agent.mcp_client import PineLabsActionClient
    from datetime import timedelta

    client = PineLabsActionClient()
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
    end = now.strftime("%Y-%m-%dT23:59:59")
    result = client.get_settlements(start, end, page=1, per_page=10)
    return {
        "start_date": start,
        "end_date": end,
        "api_endpoint": "GET /api/settlements/v1/list",
        **result,
    }


# ─── Approve / Dismiss endpoints ────────────────────────

@app.post("/api/actions/{index}/approve")
async def approve_action(index: int):
    """Merchant approves a flagged anomaly action."""
    results_list = latest_results.get("results", [])
    if index < 0 or index >= len(results_list):
        return {"status": "error", "message": "Invalid index"}

    result = results_list[index]
    action = result.get("decision", {}).get("action", "")

    executable_actions = ("auto_refund", "cancel_duplicate")
    if action in executable_actions:
        # In sandbox mode, simulate execution
        result["execution"] = {
            "status": "EXECUTED",
            "method": "merchant_approved",
            "note": f"Merchant approved {action}",
            "time": _now(),
        }
    else:
        result["execution"] = {
            "status": "EXECUTED",
            "method": "merchant_approved",
            "note": f"Merchant approved: {action}",
            "time": _now(),
        }

    log_entry = {
        "type": "decision",
        "message": f"Merchant APPROVED action '{action}' on {result.get('anomaly', {}).get('order_id', 'unknown')}",
        "time": _now(),
    }
    latest_results.setdefault("log_entries", []).append(log_entry)

    await broadcast({"type": "action_update", "data": {"index": index, "result": result}})
    await broadcast({"type": "log_entry", "data": log_entry})

    return {"status": "approved", "index": index, "execution": result["execution"]}


@app.post("/api/actions/{index}/dismiss")
async def dismiss_action(index: int):
    """Merchant dismisses a flagged anomaly."""
    results_list = latest_results.get("results", [])
    if index < 0 or index >= len(results_list):
        return {"status": "error", "message": "Invalid index"}

    result = results_list[index]
    result["execution"] = {
        "status": "dismissed",
        "reason": "Merchant dismissed",
        "time": _now(),
    }

    log_entry = {
        "type": "info",
        "message": f"Merchant DISMISSED anomaly on {result.get('anomaly', {}).get('order_id', 'unknown')}",
        "time": _now(),
    }
    latest_results.setdefault("log_entries", []).append(log_entry)

    await broadcast({"type": "action_update", "data": {"index": index, "result": result}})
    await broadcast({"type": "log_entry", "data": log_entry})

    return {"status": "dismissed", "index": index}


# Wire up webhook → agent callback
async def on_webhook_event(event_type: str, event_data: dict):
    logger.info(f"Processing webhook event: {event_type}")
    # Notify dashboard before starting scan
    await broadcast({
        "type": "webhook_received",
        "data": {
            "event_type": event_type,
            "order_id": event_data.get("order_id", ""),
            "time": _now(),
        }
    })
    await trigger_scan()


set_agent_callback(on_webhook_event)


def _now():
    return datetime.now(timezone.utc).isoformat()
