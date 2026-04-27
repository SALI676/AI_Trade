"""
main.py - AI Trade Bot Entry Point
====================================
Claude AI decides everything:
  - Buy / Sell / Hold
  - Lot size (based on confidence + account balance)
  - Stop loss price
  - Take profit price
  - Move to breakeven
  - Cut loss early
  - Trail / modify SL-TP

This file only orchestrates the loop.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from config import TradingConfig # type: ignore
from mt5_connector import MT5Connector
from claude_analyst import ClaudeAnalyst
from trade_manager import TradeManager
from risk_manager import RiskManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(f'logs/trading_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('AITradeBot')


class AITradeBot:
    def __init__(self):
        self.config   = TradingConfig()
        self.mt5      = MT5Connector(self.config)
        self.analyst  = ClaudeAnalyst(self.config)
        self.risk_mgr = RiskManager(self.config)
        self.trade_mgr = TradeManager(self.mt5, self.config)
        self.running  = False

    def setup_signals(self):
        def shutdown(sig, frame):
            logger.info("Shutdown signal received.")
            self.running = False
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

    async def run(self):
        logger.info("=" * 60)
        logger.info("  AI Trade Bot - Groq AI + MT5 (XAUUSD)")
        logger.info("  All decisions made by AI")
        logger.info("=" * 60)

        if not self.mt5.connect():
            logger.error("Failed to connect to MT5. Exiting.")
            return

        self.running = True
        self.setup_signals()
        logger.info(f"Symbol: {self.config.SYMBOL} | Interval: {self.config.ANALYSIS_INTERVAL_MINUTES} min")

        cycle = 0
        while self.running:
            cycle += 1
            logger.info(f"\n{'-'*55}")
            logger.info(f"Cycle #{cycle} -- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            try:
                await self._cycle()
            except Exception as e:
                logger.error(f"Cycle error: {e}", exc_info=True)

            logger.info(f"Waiting {self.config.ANALYSIS_INTERVAL_MINUTES} min for next cycle...")
            await asyncio.sleep(self.config.ANALYSIS_INTERVAL_MINUTES * 60)

        self.mt5.disconnect()
        logger.info("Bot stopped.")

    async def _cycle(self):
        # 1. Gather data
        market_data    = self.mt5.get_market_data(
            symbol=self.config.SYMBOL,
            timeframes=self.config.ANALYSIS_TIMEFRAMES,
            bars=self.config.BARS_TO_ANALYZE,
        )
        account_info   = self.mt5.get_account_info()
        open_positions = self.mt5.get_open_positions(self.config.SYMBOL)

        logger.info(f"Open positions: {len(open_positions)} | "
                    f"Balance: {account_info.get('balance', 0):.2f} | "
                    f"Equity: {account_info.get('equity', 0):.2f}")

        # 2. Ask AI for complete decision
        logger.info("Asking AI for full trade decision...")
        analysis = await self.analyst.analyze({
            "market_data":    market_data,
            "account_info":   account_info,
            "open_positions": open_positions,
        })

        if not analysis:
            logger.warning("No analysis from AI. Skipping cycle.")
            return

        logger.info(
            f"AI -> action={analysis['action'].upper()} | "
            f"confidence={analysis['confidence']}% | "
            f"bias={analysis.get('market_bias','?')} | "
            f"volatility={analysis.get('volatility','?')}"
        )
        logger.info(f"Reason: {analysis.get('reason','')}")

        if analysis.get("warnings"):
            for w in analysis["warnings"]:
                logger.warning(f"[WARNING] AI: {w}")

        # 3. Safety guardrails (kill switch only)
        if not self.risk_mgr.approve(analysis, account_info, open_positions):
            # Safety blocked new trade -- but still let AI manage existing positions
            analysis["action"] = "manage"
            logger.info("Safety guardrail blocked new trade. Will still manage open positions.")

        # 4. Execute AI's full decision
        self.trade_mgr.execute(analysis, open_positions)


if __name__ == "__main__":
    import os
    os.makedirs("logs", exist_ok=True)
    bot = AITradeBot()
    asyncio.run(bot.run())