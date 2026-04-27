"""
risk_manager.py - Safety Guardrails Only
=========================================
This module does NOT make trading decisions.
Claude decides lot size, SL, TP, BE, cut — all of it.

This module only provides hard safety stops:
  - Daily loss limit  (kill switch)
  - Margin level check (prevent margin call)
  - Lot size cap (prevent hallucinated huge lots)
"""

import logging
from typing import Dict, List
from datetime import date

logger = logging.getLogger('RiskManager')


class RiskManager:
    """Hard safety guardrails — Claude decides everything else."""

    def __init__(self, config):
        self.config = config
        self._daily = {"date": date.today(), "loss": 0.0, "trades": 0}

    def approve(self, analysis: Dict, account: Dict, open_positions: List[Dict]) -> bool:
        """
        Hard-stop checks only. Returns False to block execution.
        Claude's confidence, lot size, and trade logic are NOT evaluated here.
        """
        action = analysis.get("action", "hold")

        # Only gate new trade entries
        if action not in ("buy", "sell"):
            return True

        new_trade = analysis.get("new_trade")
        balance   = account.get("balance", 0)

        # ── 1. Daily loss kill switch ──
        self._refresh_daily()
        if balance > 0:
            daily_loss_pct = (self._daily["loss"] / balance) * 100
            if daily_loss_pct >= self.config.DAILY_LOSS_LIMIT_PCT:
                logger.warning(
                    f"🛑 DAILY LOSS LIMIT reached: {daily_loss_pct:.1f}% >= {self.config.DAILY_LOSS_LIMIT_PCT}%. "
                    f"No new trades today."
                )
                return False

        # ── 2. Margin level check ──
        margin_level = account.get("margin_level", 999)
        if 0 < margin_level < 120:
            logger.warning(f"🛑 Margin level critical: {margin_level:.0f}%. Blocking new trade.")
            return False

        # ── 3. Max open positions cap ──
        if len(open_positions) >= self.config.MAX_OPEN_TRADES:
            logger.info(
                f"Max open trades ({self.config.MAX_OPEN_TRADES}) reached. "
                f"Claude should manage existing positions."
            )
            return False

        # ── 4. Lot size hard cap (catch AI hallucination) ──
        if new_trade:
            lot = new_trade.get("lot_size", 0)
            if lot > self.config.MAX_LOT_SIZE:
                logger.warning(
                    f"Claude requested {lot} lots — exceeds hard cap {self.config.MAX_LOT_SIZE}. "
                    f"Will be clamped in TradeManager."
                )
                # Don't block — TradeManager will clamp it

        logger.info("✅ Safety check passed.")
        return True

    def record_closed(self, profit: float):
        """Track daily P&L for the kill switch."""
        self._refresh_daily()
        if profit < 0:
            self._daily["loss"] += abs(profit)
        self._daily["trades"] += 1
        logger.info(
            f"Trade closed | P&L: {profit:+.2f} | "
            f"Daily loss so far: {self._daily['loss']:.2f}"
        )

    def _refresh_daily(self):
        if self._daily["date"] != date.today():
            self._daily = {"date": date.today(), "loss": 0.0, "trades": 0}
