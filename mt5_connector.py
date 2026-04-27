"""
mt5_connector.py - MetaTrader 5 Interface
==========================================
Handles all communication with the MT5 terminal.
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

logger = logging.getLogger('MT5Connector')

# MetaTrader5 timeframe map
TF_MAP = {
    "M1":  1,
    "M5":  5,
    "M15": 15,
    "M30": 30,
    "H1":  16385,
    "H4":  16388,
    "D1":  16408,
}

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5 package not installed. Running in DEMO mode.")


class MT5Connector:
    """Manages MT5 connection, data retrieval, and trade execution."""

    def __init__(self, config):
        self.config = config
        self.connected = False

    # ─────────────────────────────────────────
    # Connection
    # ─────────────────────────────────────────

    def connect(self) -> bool:
        if not MT5_AVAILABLE:
            logger.info("[DEMO] Simulated MT5 connection established.")
            self.connected = True
            return True

        kwargs = {}
        if self.config.MT5_PATH:
            kwargs["path"] = self.config.MT5_PATH

        if not mt5.initialize(**kwargs):
            logger.error(f"MT5 initialize() failed: {mt5.last_error()}")
            return False

        if self.config.MT5_LOGIN:
            authorized = mt5.login(
                login=self.config.MT5_LOGIN,
                password=self.config.MT5_PASSWORD,
                server=self.config.MT5_SERVER
            )
            if not authorized:
                logger.error(f"MT5 login failed: {mt5.last_error()}")
                mt5.shutdown()
                return False

        info = mt5.account_info()
        logger.info(f"Connected to MT5 | Account: {info.login} | "
                    f"Balance: {info.balance:.2f} {info.currency} | "
                    f"Broker: {info.company}")
        self.connected = True
        return True

    def disconnect(self):
        if MT5_AVAILABLE and self.connected:
            mt5.shutdown()
            logger.info("MT5 disconnected.")
        self.connected = False

    # ─────────────────────────────────────────
    # Market Data
    # ─────────────────────────────────────────

    def get_market_data(self, symbol: str, timeframes: List[str], bars: int) -> Dict[str, Any]:
        """Fetch OHLCV data for multiple timeframes + indicators."""
        result = {}

        for tf_str in timeframes:
            df = self._get_ohlcv(symbol, tf_str, bars)
            if df is not None and not df.empty:
                df = self._add_indicators(df)
                result[tf_str] = self._df_to_summary(df, tf_str)

        # Current tick
        result["tick"] = self._get_tick(symbol)
        return result

    def _get_ohlcv(self, symbol: str, tf_str: str, bars: int) -> Optional[pd.DataFrame]:
        if not MT5_AVAILABLE:
            return self._generate_demo_data(bars)

        tf_code = TF_MAP.get(tf_str)
        if tf_code is None:
            logger.warning(f"Unknown timeframe: {tf_str}")
            return None

        rates = mt5.copy_rates_from_pos(symbol, tf_code, 0, bars)
        if rates is None or len(rates) == 0:
            logger.warning(f"No rates for {symbol} {tf_str}")
            return None

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def _get_tick(self, symbol: str) -> Dict:
        if not MT5_AVAILABLE:
            demo_price = 2320.50
            return {"bid": demo_price, "ask": demo_price + 0.30, "time": datetime.now().isoformat()}

        tick = mt5.symbol_info_tick(symbol)
        if tick:
            return {"bid": tick.bid, "ask": tick.ask, "time": datetime.fromtimestamp(tick.time).isoformat()}
        return {}

    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators to OHLCV data."""
        close = df['close']
        high  = df['high']
        low   = df['low']

        # Moving Averages
        df['ema_20']  = close.ewm(span=20,  adjust=False).mean()
        df['ema_50']  = close.ewm(span=50,  adjust=False).mean()
        df['ema_200'] = close.ewm(span=200, adjust=False).mean()
        df['sma_20']  = close.rolling(20).mean()

        # RSI
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, np.nan)
        df['rsi'] = 100 - (100 / (1 + rs))

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        df['macd']        = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist']   = df['macd'] - df['macd_signal']

        # Bollinger Bands
        df['bb_mid']   = close.rolling(20).mean()
        bb_std         = close.rolling(20).std()
        df['bb_upper'] = df['bb_mid'] + 2 * bb_std
        df['bb_lower'] = df['bb_mid'] - 2 * bb_std
        df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']

        # ATR
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low  - close.shift()).abs()
        df['atr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean()

        # Stochastic
        low14  = low.rolling(14).min()
        high14 = high.rolling(14).max()
        df['stoch_k'] = 100 * (close - low14) / (high14 - low14 + 1e-9)
        df['stoch_d'] = df['stoch_k'].rolling(3).mean()

        # Support / Resistance (recent swing highs/lows)
        df['swing_high'] = high.rolling(5, center=True).max()
        df['swing_low']  = low.rolling(5, center=True).min()

        return df

    def _df_to_summary(self, df: pd.DataFrame, tf_str: str) -> Dict:
        """Convert dataframe to a compact dict for Claude."""
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        # Recent candles (last 10)
        recent_candles = []
        for _, row in df.tail(10).iterrows():
            recent_candles.append({
                "time":  str(row.get('time', '')),
                "open":  round(float(row['open']),  2),
                "high":  round(float(row['high']),  2),
                "low":   round(float(row['low']),   2),
                "close": round(float(row['close']), 2),
            })

        # Key levels
        resistance = round(float(df['swing_high'].dropna().tail(20).max()), 2)
        support    = round(float(df['swing_low'].dropna().tail(20).min()),  2)

        return {
            "timeframe":       tf_str,
            "bars_analyzed":   len(df),
            "current_price":   round(float(last['close']), 2),
            "ema_20":          round(float(last['ema_20']),  2),
            "ema_50":          round(float(last['ema_50']),  2),
            "ema_200":         round(float(last['ema_200']), 2),
            "rsi":             round(float(last['rsi']),     1),
            "macd":            round(float(last['macd']),    4),
            "macd_signal":     round(float(last['macd_signal']), 4),
            "macd_hist":       round(float(last['macd_hist']),   4),
            "bb_upper":        round(float(last['bb_upper']), 2),
            "bb_lower":        round(float(last['bb_lower']), 2),
            "bb_width":        round(float(last['bb_width']), 4),
            "atr":             round(float(last['atr']),     2),
            "stoch_k":         round(float(last['stoch_k']), 1),
            "stoch_d":         round(float(last['stoch_d']), 1),
            "resistance":      resistance,
            "support":         support,
            "trend_ema":       "bullish" if last['ema_20'] > last['ema_50'] > last['ema_200'] else
                               "bearish" if last['ema_20'] < last['ema_50'] < last['ema_200'] else "mixed",
            "prev_close":      round(float(prev['close']), 2),
            "candle_change":   round(float(last['close'] - prev['close']), 2),
            "recent_candles":  recent_candles,
        }

    def _generate_demo_data(self, bars: int) -> pd.DataFrame:
        """Generate realistic XAUUSD demo data for testing."""
        np.random.seed(42)
        base = 2320.0
        dates = pd.date_range(end=datetime.now(), periods=bars, freq='15min')
        closes = base + np.cumsum(np.random.normal(0, 2, bars))
        opens  = closes + np.random.normal(0, 1, bars)
        highs  = np.maximum(opens, closes) + abs(np.random.normal(0, 2, bars))
        lows   = np.minimum(opens, closes) - abs(np.random.normal(0, 2, bars))
        vols   = np.random.randint(100, 5000, bars)
        return pd.DataFrame({'time': dates, 'open': opens, 'high': highs,
                             'low': lows, 'close': closes, 'tick_volume': vols})

    # ─────────────────────────────────────────
    # Account Info
    # ─────────────────────────────────────────

    def get_account_info(self) -> Dict:
        if not MT5_AVAILABLE:
            return {"balance": 10000.0, "equity": 10000.0, "margin_free": 9800.0,
                    "margin_level": 100.0, "profit": 0.0, "currency": "USD"}
        info = mt5.account_info()
        if not info:
            return {}
        return {
            "balance":      info.balance,
            "equity":       info.equity,
            "margin_free":  info.margin_free,
            "margin_level": info.margin_level,
            "profit":       info.profit,
            "currency":     info.currency,
        }

    def get_open_positions(self, symbol: str) -> List[Dict]:
        if not MT5_AVAILABLE:
            return []
        positions = mt5.positions_get(symbol=symbol)
        if not positions:
            return []
        result = []
        for pos in positions:
            result.append({
                "ticket":     pos.ticket,
                "type":       "buy" if pos.type == 0 else "sell",
                "volume":     pos.volume,
                "open_price": pos.price_open,
                "sl":         pos.sl,
                "tp":         pos.tp,
                "profit":     pos.profit,
                "magic":      pos.magic,
            })
        return result

    # ─────────────────────────────────────────
    # Trade Execution
    # ─────────────────────────────────────────

    def place_order(self, order: Dict) -> Optional[Dict]:
        """Place a market order on MT5."""
        if not MT5_AVAILABLE:
            logger.info(f"[DEMO] Order placed: {order}")
            return {"ticket": 999999, "retcode": 10009, **order}

        action_type = mt5.ORDER_TYPE_BUY if order['type'] == 'buy' else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(order['symbol'])
        if not tick:
            logger.error("Cannot get tick for order")
            return None

        price = tick.ask if order['type'] == 'buy' else tick.bid

        request = {
            "action":    mt5.TRADE_ACTION_DEAL,
            "symbol":    order['symbol'],
            "volume":    float(order['volume']),
            "type":      action_type,
            "price":     price,
            "sl":        order.get('sl', 0.0),
            "tp":        order.get('tp', 0.0),
            "deviation": self.config.SLIPPAGE,
            "magic":     self.config.MAGIC_NUMBER,
            "comment":   order.get('comment', 'AI Trade Bot'),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }

        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return {"ticket": result.order, "retcode": result.retcode,
                    "price": result.price, "volume": result.volume}
        else:
            logger.error(f"Order failed: retcode={result.retcode} | {result.comment}")
            return None

    def modify_position(self, ticket: int, sl: Optional[float], tp: Optional[float]) -> bool:
        """Modify SL/TP of an existing position (move to BE, trail, etc.)."""
        if not MT5_AVAILABLE:
            logger.info(f"[DEMO] Modify #{ticket}: SL={sl} TP={tp}")
            return True

        request = {
            "action":   mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl":       float(sl) if sl is not None else 0.0,
            "tp":       float(tp) if tp is not None else 0.0,
        }
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Position #{ticket} modified: SL={sl} TP={tp}")
            return True
        else:
            logger.error(f"Modify failed #{ticket}: retcode={result.retcode} | {result.comment}")
            return False

    def close_position(self, ticket: int, symbol: str, vol: float, pos_type: str) -> bool:
        """Close an existing position."""
        if not MT5_AVAILABLE:
            logger.info(f"[DEMO] Position {ticket} closed.")
            return True

        tick = mt5.symbol_info_tick(symbol)
        close_type  = mt5.ORDER_TYPE_SELL if pos_type == 'buy' else mt5.ORDER_TYPE_BUY
        close_price = tick.bid if pos_type == 'buy' else tick.ask

        request = {
            "action":    mt5.TRADE_ACTION_DEAL,
            "symbol":    symbol,
            "volume":    vol,
            "type":      close_type,
            "position":  ticket,
            "price":     close_price,
            "deviation": self.config.SLIPPAGE,
            "magic":     self.config.MAGIC_NUMBER,
            "comment":   "AI Bot Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        result = mt5.order_send(request)
        return result.retcode == mt5.TRADE_RETCODE_DONE
