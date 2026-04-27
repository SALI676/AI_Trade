"""
trade_manager.py - Trade Execution Manager
===========================================
Executes EXACTLY what Claude decided.
No overrides. No hardcoded lot sizes, SL, TP, or BE logic here.
All of that comes from Claude's JSON response.
"""

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger('TradeManager')


class TradeManager:
    """Faithfully executes Claude's trade decisions on MT5."""

    def __init__(self, mt5, config):
        self.mt5    = mt5
        self.config = config

    # ──────────────────────────────────────────────────────
    # Main dispatcher — called once per cycle
    # ──────────────────────────────────────────────────────

    def execute(self, analysis: Dict[str, Any], open_positions: List[Dict]) -> None:
        """
        Execute all decisions Claude returned:
          1. Manage existing positions (BE / cut / close / modify SL-TP)
          2. Open a new trade if instructed
        """
        action           = analysis.get("action", "hold")
        position_actions = analysis.get("position_actions", [])
        new_trade        = analysis.get("new_trade")
        confidence       = analysis.get("confidence", 0)
        reason           = analysis.get("reason", "")

        logger.info(f"Claude decision → action={action.upper()} | confidence={confidence}% | {reason}")

        # ── Step 1: Handle existing positions ──
        if action == "close_all":
            logger.info("Claude says CLOSE ALL positions.")
            for pos in open_positions:
                self._close_position(pos, reason="AI close_all")
            return

        # Process per-ticket position actions
        pos_map = {p["ticket"]: p for p in open_positions}
        for pa in position_actions:
            ticket = pa.get("ticket")
            pos    = pos_map.get(ticket)
            if pos is None:
                logger.warning(f"Ticket #{ticket} not found in open positions, skipping.")
                continue
            self._handle_position_action(pa, pos)

        # ── Step 2: Open new trade if Claude wants ──
        if action in ("buy", "sell") and new_trade:
            self._open_new_trade(action, new_trade, confidence)
        elif action == "manage":
            logger.info("Claude action=manage: only position adjustments, no new trade.")
        else:
            logger.info("Claude action=hold: no new trade opened.")

    # ──────────────────────────────────────────────────────
    # Position Management — exactly as Claude specified
    # ──────────────────────────────────────────────────────

    def _handle_position_action(self, pa: Dict, pos: Dict) -> None:
        ticket  = pa["ticket"]
        action  = pa.get("action", "hold")
        new_sl  = pa.get("new_sl")
        new_tp  = pa.get("new_tp")
        pa_reason = pa.get("reason", "")

        logger.info(f"  Position #{ticket} ({pos['type'].upper()}) → {action.upper()}  | {pa_reason}")

        if action == "hold":
            pass  # nothing to do

        elif action == "move_to_be":
            # Claude sets new_sl = entry price (breakeven)
            be_sl = new_sl if new_sl is not None else pos["open_price"]
            logger.info(f"    Moving SL to breakeven: {be_sl}")
            self._modify_position(ticket, sl=be_sl, tp=pos.get("tp"))

        elif action in ("cut", "close"):
            logger.info(f"    Closing position #{ticket} ({action})")
            self._close_position(pos, reason=f"AI {action}: {pa_reason}")

        elif action == "modify_sl":
            if new_sl is not None:
                logger.info(f"    Modifying SL → {new_sl}")
                self._modify_position(ticket, sl=new_sl, tp=pos.get("tp"))
            else:
                logger.warning(f"    modify_sl requested but new_sl is null for #{ticket}")

        elif action == "modify_tp":
            if new_tp is not None:
                logger.info(f"    Modifying TP → {new_tp}")
                self._modify_position(ticket, sl=pos.get("sl"), tp=new_tp)
            else:
                logger.warning(f"    modify_tp requested but new_tp is null for #{ticket}")

        else:
            logger.warning(f"    Unknown position action '{action}' for #{ticket}")

    # ──────────────────────────────────────────────────────
    # New Trade — Claude's exact lot, SL, TP
    # ──────────────────────────────────────────────────────

    def _open_new_trade(self, direction: str, new_trade: Dict, confidence: int) -> None:
        lot_size   = new_trade.get("lot_size")
        stop_loss  = new_trade.get("stop_loss")
        take_profit = new_trade.get("take_profit")
        rr         = new_trade.get("risk_reward", "?")
        note       = new_trade.get("entry_note", "")

        # Validate Claude provided what we need
        if lot_size is None or stop_loss is None or take_profit is None:
            logger.error(f"Claude's new_trade is missing lot/SL/TP: {new_trade}")
            return

        # Safety cap (prevents a hallucinated huge lot)
        lot_size = round(min(float(lot_size), self.config.MAX_LOT_SIZE), 2)
        lot_size = max(lot_size, 0.01)

        logger.info(f"Opening {direction.upper()} | Lot={lot_size} | SL={stop_loss} | "
                    f"TP={take_profit} | R:R={rr} | Confidence={confidence}%")
        logger.info(f"  Entry note: {note}")

        order = {
            "symbol":  self.config.SYMBOL,
            "type":    direction,
            "volume":  lot_size,
            "sl":      float(stop_loss),
            "tp":      float(take_profit),
            "comment": f"AI:{confidence}%",
        }

        result = self.mt5.place_order(order)
        if result:
            logger.info(f"  ✅ Trade opened → Ticket #{result.get('ticket')} @ {result.get('price')}")
        else:
            logger.warning("  ❌ Trade execution failed.")

    # ──────────────────────────────────────────────────────
    # MT5 Helpers
    # ──────────────────────────────────────────────────────

    def _close_position(self, pos: Dict, reason: str = "") -> bool:
        logger.info(f"  Closing #{pos['ticket']} | P&L: {pos.get('profit', 0):.2f} | {reason}")
        return self.mt5.close_position(
            ticket   = pos["ticket"],
            symbol   = self.config.SYMBOL,
            vol      = pos["volume"],
            pos_type = pos["type"],
        )

    def _modify_position(self, ticket: int, sl: Optional[float], tp: Optional[float]) -> bool:
        return self.mt5.modify_position(ticket=ticket, sl=sl, tp=tp)
