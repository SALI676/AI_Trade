"""
config.py - Trading Bot Configuration
=====================================
Edit these settings to customize your trading bot.
"""

import os
from dotenv import load_dotenv # type: ignore

load_dotenv()


class TradingConfig:
    # -----------------------------------------
    # MT5 Connection
    # -----------------------------------------
    MT5_LOGIN    = int(os.getenv("MT5_LOGIN", "0"))
    MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
    MT5_SERVER   = os.getenv("MT5_SERVER",   "")
    MT5_PATH     = os.getenv("MT5_PATH",     "C:/Program Files/MetaTrader 5/terminal64.exe")

    # -----------------------------------------
    # Groq AI (Free)
    # -----------------------------------------
    GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL    = "llama-3.1-8b-instant"      # Faster, uses 4x fewer tokens
    MAX_TOKENS    = 1500

    # -----------------------------------------
    # Symbol & Timeframes
    # -----------------------------------------
    SYMBOL           = "XAUUSD"
    TIMEFRAME_STR    = "M5"
    BARS_TO_ANALYZE  = 50                        # Reduced from 100 to save tokens
    ANALYSIS_TIMEFRAMES = ["M5", "M15", "H1", "H4"]

    # -----------------------------------------
    # Trade Execution
    # -----------------------------------------
    LOT_SIZE              = 0.01
    MAX_LOT_SIZE          = 1
    MAGIC_NUMBER          = 202401
    SLIPPAGE              = 10

    # -----------------------------------------
    # Risk Management
    # -----------------------------------------
    MAX_RISK_PERCENT      = 1.5
    STOP_LOSS_PIPS        = 150
    TAKE_PROFIT_PIPS      = 300
    MAX_OPEN_TRADES       = 2
    MIN_CONFIDENCE        = 70                   # Kept at 70 to protect your account
    DAILY_LOSS_LIMIT_PCT  = 3.0

    # -----------------------------------------
    # Bot Timing
    # -----------------------------------------
    ANALYSIS_INTERVAL_MINUTES = 15

    def to_dict(self):
        return {
            "symbol": self.SYMBOL,
            "timeframe": self.TIMEFRAME_STR,
            "lot_size": self.LOT_SIZE,
            "max_lot_size": self.MAX_LOT_SIZE,
            "stop_loss_pips": self.STOP_LOSS_PIPS,
            "take_profit_pips": self.TAKE_PROFIT_PIPS,
            "max_open_trades": self.MAX_OPEN_TRADES,
            "min_confidence": self.MIN_CONFIDENCE,
            "max_risk_percent": self.MAX_RISK_PERCENT,
        }