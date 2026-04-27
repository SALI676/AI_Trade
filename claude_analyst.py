"""
claude_analyst.py - AI Market Analyst (Groq / Llama)
=====================================================
AI decides EVERYTHING: entry, lot size, SL, TP, move-to-BE, cut loss.
No hardcoded trade logic — pure AI judgment.
"""

import json
import logging
from groq import Groq
from typing import Optional, Dict, Any

logger = logging.getLogger('ClaudeAnalyst')


SYSTEM_PROMPT = """You are an expert algorithmic forex trader specializing in XAUUSD (Gold/USD).

You have FULL CONTROL over every trade decision. You decide:
- Whether to BUY, SELL, HOLD, or do nothing
- Exact LOT SIZE based on your confidence and account balance
- Exact STOP LOSS price (actual price level, not pips)
- Exact TAKE PROFIT price (actual price level, not pips)
- Whether to MOVE existing positions to BREAKEVEN
- Whether to CUT (close) a losing position early
- Whether to CLOSE a winning position early (lock in profit)
- Whether to MODIFY SL/TP of existing positions (trail stop)

You analyze price action, market structure, momentum, and account state.
Capital preservation is your top priority.

═══════════════════════════════════════════════════════
RESPONSE FORMAT — Reply ONLY with valid JSON, no extra text:
═══════════════════════════════════════════════════════
{
  "action": "buy" | "sell" | "hold" | "close_all" | "manage",
  "confidence": <integer 0-100>,
  "reason": "<your reasoning, 2-3 sentences>",

  "new_trade": {
    "lot_size": <float, e.g. 0.05>,
    "stop_loss": <float, exact price>,
    "take_profit": <float, exact price>,
    "risk_reward": <float>,
    "entry_note": "<why this entry>"
  } | null,

  "position_actions": [
    {
      "ticket": <int>,
      "action": "hold" | "move_to_be" | "cut" | "close" | "modify_sl" | "modify_tp",
      "new_sl": <float or null>,
      "new_tp": <float or null>,
      "reason": "<why>"
    }
  ],

  "market_bias": "bullish" | "bearish" | "neutral",
  "volatility": "low" | "medium" | "high",
  "warnings": ["<any risk warnings>"]
}

═══════════════════════════════════════════════════════
YOUR DECISION RULES:
═══════════════════════════════════════════════════════
LOT SIZE — you calculate based on your confidence:
  confidence 90-100% → risk up to 3.0% of account balance
  confidence 80-89%  → risk up to 2.0% of account balance
  confidence 70-79%  → risk up to 1.0% of account balance
  confidence < 70%   → set action="hold", new_trade=null

  Formula: lot_size = (balance × risk_pct) / (sl_distance_in_pips × 10)
  Round to 0.01. Maximum 0.50 lots.

MOVE TO BREAKEVEN (move_to_be):
  Trigger: position profit has reached 1R (risk amount in USD)
  Action: set new_sl = original entry price

CUT LOSS EARLY (cut):
  Trigger: market structure clearly broken against the trade
  Trigger: higher timeframe gives strong opposing signal

CLOSE EARLY (close):
  Trigger: strong reversal pattern forming near TP zone
  Trigger: momentum clearly fading before TP reached

TRAIL STOP (modify_sl):
  Trigger: price has moved 2R in your favor
  Action: trail SL to lock in at least 1R profit

HOLD:
  If no new opportunity and existing positions are well-managed → hold.
  Still list each open ticket in position_actions with action="hold".
"""


class ClaudeAnalyst:
    """Groq AI makes ALL decisions — entry, sizing, BE, cut, trail."""

    def __init__(self, config):
        self.config = config
        self.client = Groq(api_key=config.GROQ_API_KEY)

    async def analyze(self, context: Dict[str, Any]) -> Optional[Dict]:
        prompt = self._build_prompt(context)
        try:
            response = self.client.chat.completions.create(
                model=self.config.GROQ_MODEL,
                max_tokens=self.config.MAX_TOKENS,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt}
                ]
            )
            raw_text = response.choices[0].message.content.strip()
            logger.debug(f"Groq raw response:\n{raw_text}")
            return self._parse_response(raw_text)
        except Exception as e:
            logger.error(f"Groq API error: {e}", exc_info=True)
            return None

    def _build_prompt(self, context: Dict[str, Any]) -> str:
        market    = context.get("market_data", {})
        account   = context.get("account_info", {})
        positions = context.get("open_positions", [])
        tick      = market.get("tick", {})
        bid       = tick.get("bid", "N/A")
        ask       = tick.get("ask", "N/A")

        lines = [
            "## XAUUSD — Full Trade Decision Request",
            "",
            f"Live Price : Bid={bid}  Ask={ask}",
            f"Balance    : {account.get('balance', 0):.2f} {account.get('currency','USD')}",
            f"Equity     : {account.get('equity', 0):.2f}",
            f"Free Margin: {account.get('margin_free', 0):.2f}",
            f"Daily P&L  : {account.get('profit', 0):.2f}",
            "",
        ]

        if positions:
            lines.append("## Open Positions (decide what to do with EACH ticket):")
            lines.append("")
            for p in positions:
                entry     = p['open_price']
                cur_price = bid if p['type'] == 'buy' else ask
                try:
                    cur_price = float(str(cur_price))
                except Exception:
                    cur_price = entry

                pip_move   = (cur_price - entry) if p['type'] == 'buy' else (entry - cur_price)
                pip_move   = round(pip_move / 0.10, 1)
                sl         = p.get('sl', 0) or 0
                one_r_price = abs(entry - sl) if sl else None
                r_multiple  = round(abs(cur_price - entry) / one_r_price, 2) if one_r_price else "?"

                lines += [
                    f"  Ticket #{p['ticket']}",
                    f"    Type         : {p['type'].upper()}  ({p['volume']} lots)",
                    f"    Entry        : {entry}",
                    f"    Current Price: {cur_price}",
                    f"    Current SL   : {sl if sl else 'Not set'}",
                    f"    Current TP   : {p.get('tp', 'Not set')}",
                    f"    Pips Moved   : {pip_move:+.1f} pips",
                    f"    P&L (USD)    : {p.get('profit', 0):.2f}",
                    f"    R Multiple   : {r_multiple}R  (1R = {round(one_r_price / 0.10, 1) if one_r_price else '?'} pips)",
                    f"    Breakeven at : {entry}  <- move SL here when profit >= 1R",
                    "",
                ]
        else:
            lines += ["## Open Positions: None", ""]

        lines.append("## Multi-Timeframe Technical Data:")
        for tf in ["M5", "M15", "H1", "H4"]:
            d = market.get(tf)
            if not d:
                continue
            rsi_warn = " <- OVERBOUGHT" if d['rsi'] > 70 else (" <- OVERSOLD" if d['rsi'] < 30 else "")
            lines += [
                "",
                f"### {tf} ({d.get('bars_analyzed', 0)} bars)",
                f"  Price    : {d['current_price']}  (prev {d.get('prev_close','?')}, chg {d.get('candle_change',0):+.2f})",
                f"  EMA 20   : {d['ema_20']}",
                f"  EMA 50   : {d['ema_50']}",
                f"  EMA 200  : {d['ema_200']}",
                f"  Trend    : {d['trend_ema'].upper()}",
                f"  RSI(14)  : {d['rsi']}{rsi_warn}",
                f"  Stoch K/D: {d['stoch_k']} / {d['stoch_d']}",
                f"  MACD     : {d['macd']}  Signal: {d['macd_signal']}  Hist: {d['macd_hist']}",
                f"  BB Upper : {d['bb_upper']}",
                f"  BB Lower : {d['bb_lower']}",
                f"  ATR(14)  : {d['atr']}",
                f"  Resist   : {d['resistance']}",
                f"  Support  : {d['support']}",
            ]
            candles = d.get("recent_candles", [])
            if candles:
                lines.append("  Recent candles:")
                for c in candles[-5:]:
                    body = c['close'] - c['open']
                    tag  = "BULL" if body > 0 else "BEAR"
                    lines.append(f"    {c['time'][-8:-3]}  O:{c['open']}  H:{c['high']}  L:{c['low']}  C:{c['close']}  {tag}")

        lines += [
            "",
            "## Your Instructions:",
            "1. For EACH open ticket decide: hold / move_to_be / cut / close / modify_sl / modify_tp",
            "2. Decide: open a new trade (buy/sell) or hold?",
            "3. If new trade: set exact lot_size, stop_loss price, take_profit price",
            "4. Lot size must be calculated from your confidence + account balance",
            "5. Reply with ONLY the JSON object.",
        ]

        return "\n".join(lines)

    def _parse_response(self, text: str) -> Optional[Dict]:
        text = text.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text  = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}\nRaw: {text[:500]}")
            return None

        data["action"]     = data.get("action", "hold").lower().strip()
        data["confidence"] = int(data.get("confidence", 0))

        if data["action"] not in ("buy", "sell", "hold", "close_all", "manage"):
            data["action"] = "hold"

        if not isinstance(data.get("position_actions"), list):
            data["position_actions"] = []

        return data