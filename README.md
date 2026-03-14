# MerchantMind

**Autonomous Reconciliation Agent for Pine Labs**

MerchantMind is an AI-powered agent that monitors merchant transactions in real-time, detects settlement anomalies, and takes autonomous corrective action via Pine Labs APIs.

## The Problem

Indian merchants lose **₹2,800 crore annually** to settlement mismatches. A customer pays ₹1,500 but only ₹1,300 reaches the merchant. Duplicate refunds slip through. Fraud patterns go unnoticed. Merchants discover these issues days or weeks later — if ever.

## The Solution

MerchantMind runs a 5-stage AI pipeline that watches every transaction, detects 10 types of anomalies, reasons about each one using Claude AI, and executes corrective actions — all without human intervention.

```
Pine Labs Webhooks → FastAPI Backend → LangGraph Agent → Claude AI
                                              ↓
                                   Pine Labs REST API (refunds/cancels)
                                              ↓
                                   React Dashboard (real-time WebSocket)
```

## Features

- **10 Anomaly Detection Patterns** — settlement shortfall, duplicate refund, refund velocity fraud, over-settlement, late settlement, refund exceeds capture, duplicate order, high-value outlier, partial capture mismatch, midnight burst
- **Claude AI Reasoning** — per-anomaly analysis with transparent explanations and confidence scores
- **Real Pine Labs API Integration** — refunds, cancellations, order lookups, and settlement data via live API calls
- **Real-Time Dashboard** — WebSocket-powered streaming with animated counters, severity filters, and clickable status filters
- **Webhook-Triggered Scans** — Pine Labs payment events auto-trigger the agent
- **Approve/Dismiss Actions** — merchants stay in control of flagged items
- **Dark/Light Theme** — Bloomberg terminal aesthetic

## Pine Labs API Integration

| API | Endpoint | Status |
|-----|----------|--------|
| Auth | `POST /api/auth/v1/token` | Working |
| Orders | `GET /api/pay/v1/orders/{id}` | Working |
| Refunds | `POST /api/pay/v1/refunds/{id}` | Working (real refund executed) |
| Cancel | `PUT /api/pay/v1/orders/{id}/cancel` | Working |
| Settlements | `GET /api/settlements/v1/list` | Working (sandbox has 0 records) |
| Payment Links | `POST /api/pay/v1/paymentlink` | Working |

## Tech Stack

- **Agent**: LangGraph (5-node StateGraph pipeline)
- **AI**: Claude Sonnet 4 (Anthropic API)
- **Backend**: FastAPI + WebSocket
- **Frontend**: React
- **APIs**: Pine Labs Plural v2 REST API
- **Deployment**: AWS EC2

## Quick Start

### Backend
```bash
cd merchantmind
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set environment variables
export PINE_LABS_CLIENT_ID=your_client_id
export PINE_LABS_CLIENT_SECRET=your_client_secret
export ANTHROPIC_API_KEY=your_api_key

# Generate mock data
python data/generate_mock.py

# Start backend
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd dashboard
npm install
npm start
```

Dashboard runs at `http://localhost:3000`, backend at `http://localhost:8000`.

## Architecture

```
┌──────────────────────────────────────────────────┐
│              React Dashboard (port 3000)          │
│   WebSocket: /ws/agent-log (real-time streaming) │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│              FastAPI Backend (port 8000)           │
│  POST /api/scan         — trigger agent           │
│  GET  /api/anomalies    — fetch results           │
│  GET  /api/settlements  — live settlement pull    │
│  POST /webhooks/pine-labs — webhook listener      │
│  POST /api/actions/{i}/approve — merchant action  │
│  POST /api/actions/{i}/dismiss — dismiss anomaly  │
└────────────────────┬─────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────┐
│           LangGraph Agent Pipeline                │
│  load_data → detect_anomalies → llm_reason       │
│     (loop) → execute_actions → summarize         │
└───────┬──────────────┬───────────────┬───────────┘
        │              │               │
   Rule Engine    Claude Sonnet    Pine Labs API
   (10 patterns)  (reasoning)      (refunds/cancels)
```

## Real Sandbox Proof

- 3 real PROCESSED orders on Pine Labs UAT (MID 121478)
- 1 real refund executed with approval code from RBL acquirer
- Settlement API returns 200 OK with live connection

## Team

Built for the **PineLabs Agentic Ecommerce Hackathon** (March 2026)
