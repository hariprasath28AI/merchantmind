import os
from dotenv import load_dotenv

load_dotenv()

# Pine Labs
PINE_LABS_MID = os.getenv("PINE_LABS_MID")
PINE_LABS_CLIENT_ID = os.getenv("PINE_LABS_CLIENT_ID")
PINE_LABS_CLIENT_SECRET = os.getenv("PINE_LABS_CLIENT_SECRET")
PINE_LABS_BASE_URL = os.getenv("PINE_LABS_BASE_URL", "https://pluraluat.v2.pinepg.in")
PINE_LABS_MCP_URL = "https://mcp.pinelabs.com/sse"

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Agent thresholds
AUTO_REFUND_THRESHOLD_PAISE = 50000  # ₹500
FRAUD_VELOCITY_WINDOW_MINUTES = 60
FRAUD_VELOCITY_MAX_REFUNDS = 3
HIGH_VALUE_MULTIPLIER = 10  # flag if txn > 10x merchant avg
MIDNIGHT_HOUR_START = 0  # 12 AM
MIDNIGHT_HOUR_END = 5   # 5 AM
MIDNIGHT_BURST_THRESHOLD = 5  # flag if > 5 txns from same customer in window
