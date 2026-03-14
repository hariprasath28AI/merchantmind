"""LangGraph agent for MerchantMind — orchestrates anomaly detection, reasoning, and action."""
import json
import logging
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from anthropic import Anthropic

from agent.anomaly_detector import detect_all_anomalies
from agent.prompts import SYSTEM_PROMPT, build_reasoning_prompt
from agent.mcp_client import PineLabsActionClient
from config import ANTHROPIC_API_KEY, AUTO_REFUND_THRESHOLD_PAISE

logger = logging.getLogger(__name__)

client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


class AgentState(TypedDict):
    transactions: list
    settlements: list
    anomalies: list
    current_anomaly_index: int
    results: list
    log_entries: list  # for real-time dashboard streaming


def load_data(state: AgentState) -> dict:
    """Load transaction and settlement data from mock JSON files + real Pine Labs Settlement API."""
    from datetime import datetime, timedelta

    with open("data/mock_transactions.json") as f:
        transactions = json.load(f)
    with open("data/mock_settlements.json") as f:
        settlements = json.load(f)

    log = state.get("log_entries", [])
    log.append({
        "step": "load_data",
        "message": f"Loaded {len(transactions)} transactions and {len(settlements)} settlements from local data",
        "type": "info",
    })

    # Attempt to pull real settlements from Pine Labs Settlement API
    try:
        action_client = PineLabsActionClient()
        now = datetime.utcnow()
        start = (now - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")
        end = now.strftime("%Y-%m-%dT23:59:59")
        result = action_client.get_settlements(start, end, page=1, per_page=10)

        if result["status"] == "fetched":
            count = result["total_count"]
            amount = result["total_amount"]
            log.append({
                "step": "load_data",
                "message": f"Pine Labs Settlement API: {count} settlements fetched (₹{amount:,.2f} total) — live API call",
                "type": "decision" if count > 0 else "info",
            })
        else:
            log.append({
                "step": "load_data",
                "message": "Pine Labs Settlement API: connected but no settlement data on sandbox",
                "type": "info",
            })
    except Exception as e:
        logger.warning(f"Settlement API pull failed: {e}")
        log.append({
            "step": "load_data",
            "message": f"Pine Labs Settlement API: unavailable ({str(e)[:50]})",
            "type": "warning",
        })

    return {
        "transactions": transactions,
        "settlements": settlements,
        "anomalies": [],
        "current_anomaly_index": 0,
        "results": [],
        "log_entries": log,
    }


def detect_anomalies(state: AgentState) -> dict:
    """Run rule-based anomaly detection."""
    anomalies = detect_all_anomalies(state["transactions"], state["settlements"])

    log = state.get("log_entries", [])
    log.append({
        "step": "detect_anomalies",
        "message": f"Detected {len(anomalies)} anomalies across {len(state['transactions'])} transactions",
        "type": "warning" if anomalies else "info",
        "anomaly_count": len(anomalies),
    })

    severity_counts = {}
    for a in anomalies:
        s = a["severity"]
        severity_counts[s] = severity_counts.get(s, 0) + 1

    if severity_counts:
        log.append({
            "step": "detect_anomalies",
            "message": f"Severity breakdown: {severity_counts}",
            "type": "info",
        })

    return {
        **state,
        "anomalies": anomalies,
        "current_anomaly_index": 0,
        "log_entries": log,
    }


def llm_reason(state: AgentState) -> dict:
    """Use Claude to reason about the current anomaly."""
    idx = state["current_anomaly_index"]
    anomalies = state["anomalies"]
    results = list(state.get("results", []))
    log = list(state.get("log_entries", []))

    if idx >= len(anomalies):
        return {**state, "results": results, "log_entries": log}

    anomaly = anomalies[idx]

    log.append({
        "step": "llm_reason",
        "message": f"Analyzing anomaly {idx + 1}/{len(anomalies)}: {anomaly['type']} on {anomaly['order_id']}",
        "type": "processing",
        "anomaly_type": anomaly["type"],
    })

    prompt = build_reasoning_prompt(anomaly)

    if client:
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            decision_text = response.content[0].text

            # Parse JSON from response
            try:
                # Handle markdown code blocks
                text = decision_text
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0]
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0]
                decision = json.loads(text.strip())
            except (json.JSONDecodeError, IndexError):
                decision = {
                    "action": anomaly["recommended_action"],
                    "confidence": 0.7,
                    "reasoning": decision_text[:200],
                    "merchant_summary": f"Anomaly detected: {anomaly['type']}",
                    "risk_level": anomaly["severity"],
                }

            log.append({
                "step": "llm_reason",
                "message": f"Decision: {decision.get('action')} (confidence: {decision.get('confidence', 'N/A')})",
                "type": "decision",
                "reasoning": decision.get("reasoning", ""),
            })

        except Exception as e:
            logger.error(f"LLM error: {e}")
            decision = {
                "action": anomaly["recommended_action"],
                "confidence": 0.5,
                "reasoning": f"Fallback to rule engine (LLM unavailable: {str(e)[:50]})",
                "merchant_summary": f"Anomaly detected: {anomaly['type']} on {anomaly['order_id']}",
                "risk_level": anomaly["severity"],
            }
    else:
        # No API key — use rule engine recommendation
        decision = {
            "action": anomaly["recommended_action"],
            "confidence": 0.8,
            "reasoning": f"Rule-based detection: {anomaly['type']}",
            "merchant_summary": f"Anomaly detected: {anomaly['type']} on order {anomaly['order_id']}",
            "risk_level": anomaly["severity"],
        }

    result = {
        "anomaly": {
            "type": anomaly["type"],
            "severity": anomaly["severity"],
            "order_id": anomaly["order_id"],
            "details": anomaly["details"],
        },
        "decision": decision,
    }
    results.append(result)

    return {
        **state,
        "current_anomaly_index": idx + 1,
        "results": results,
        "log_entries": log,
    }


def should_continue(state: AgentState) -> str:
    """Check if there are more anomalies to process."""
    if state["current_anomaly_index"] < len(state["anomalies"]):
        return "continue"
    return "done"


def execute_actions(state: AgentState) -> dict:
    """Execute decided actions via Pine Labs API — auto-refund, cancel, etc."""
    results = list(state.get("results", []))
    log = list(state.get("log_entries", []))
    action_client = PineLabsActionClient()

    executable_actions = {"auto_refund", "cancel_duplicate"}
    executed_count = 0
    simulated_count = 0

    log.append({
        "step": "execute_actions",
        "message": f"Executing actions for {len(results)} anomalies...",
        "type": "processing",
    })

    for i, result in enumerate(results):
        action = result["decision"]["action"]
        order_id = result["anomaly"]["order_id"]
        details = result["anomaly"]["details"]

        if action == "auto_refund":
            amount = details.get("shortfall", details.get("captured_amount", 0))
            if amount <= AUTO_REFUND_THRESHOLD_PAISE and amount > 0:
                exec_result = action_client.create_refund(order_id, amount, reason="settlement_shortfall")
                result["execution"] = exec_result

                if exec_result["status"] == "executed":
                    executed_count += 1
                    log.append({
                        "step": "execute_actions",
                        "message": f"REFUND EXECUTED: ₹{amount/100:.0f} for {order_id} → refund_id: {exec_result.get('refund_id')}",
                        "type": "decision",
                    })
                else:
                    simulated_count += 1
                    log.append({
                        "step": "execute_actions",
                        "message": f"REFUND SIMULATED: ₹{amount/100:.0f} for {order_id} (mock order — API call attempted)",
                        "type": "info",
                    })
            else:
                result["execution"] = {"status": "flagged_only", "reason": "Amount exceeds auto-refund threshold"}
                log.append({
                    "step": "execute_actions",
                    "message": f"FLAGGED: Refund for {order_id} exceeds ₹500 threshold — needs merchant approval",
                    "type": "warning",
                })

        elif action == "cancel_duplicate":
            exec_result = action_client.cancel_order(order_id)
            result["execution"] = exec_result

            if exec_result["status"] == "executed":
                executed_count += 1
                log.append({
                    "step": "execute_actions",
                    "message": f"ORDER CANCELLED: {order_id} (duplicate)",
                    "type": "decision",
                })
            else:
                simulated_count += 1
                log.append({
                    "step": "execute_actions",
                    "message": f"CANCEL SIMULATED: {order_id} (mock order — API call attempted)",
                    "type": "info",
                })

        else:
            # Non-executable actions: block, flag, escalate, etc.
            result["execution"] = {"status": "flagged_only", "reason": f"Action '{action}' requires merchant review"}

    log.append({
        "step": "execute_actions",
        "message": f"Execution complete: {executed_count} executed, {simulated_count} simulated, {len(results) - executed_count - simulated_count} flagged only",
        "type": "summary",
    })

    return {**state, "results": results, "log_entries": log}


def summarize(state: AgentState) -> dict:
    """Generate final summary for merchant dashboard."""
    results = state.get("results", [])
    log = list(state.get("log_entries", []))

    auto_fixed = sum(1 for r in results if r["decision"]["action"] in ("auto_refund", "cancel_duplicate"))
    flagged = sum(1 for r in results if r["decision"]["action"] in ("block_and_flag", "block_refund", "fraud_alert"))
    review = sum(1 for r in results if r["decision"]["action"] in (
        "flag_for_review", "escalate_to_support", "hold_for_confirmation", "flag_unusual_activity", "flag_over_settlement"
    ))

    summary = {
        "total_anomalies": len(results),
        "auto_fixed": auto_fixed,
        "flagged": flagged,
        "pending_review": review,
        "summary_text": f"Found {len(results)} issues. Fixed {auto_fixed} automatically. {flagged} flagged as critical. {review} need your review.",
    }

    log.append({
        "step": "summarize",
        "message": summary["summary_text"],
        "type": "summary",
        "summary": summary,
    })

    return {**state, "log_entries": log, "summary": summary}


def build_agent():
    """Build and compile the LangGraph agent."""
    graph = StateGraph(AgentState)

    graph.add_node("load_data", load_data)
    graph.add_node("detect_anomalies", detect_anomalies)
    graph.add_node("llm_reason", llm_reason)
    graph.add_node("execute_actions", execute_actions)
    graph.add_node("summarize", summarize)

    graph.set_entry_point("load_data")
    graph.add_edge("load_data", "detect_anomalies")
    graph.add_edge("detect_anomalies", "llm_reason")
    graph.add_conditional_edges("llm_reason", should_continue, {
        "continue": "llm_reason",
        "done": "execute_actions",
    })
    graph.add_edge("execute_actions", "summarize")
    graph.add_edge("summarize", END)

    return graph.compile()
