# 🤖 AI Trade Bot — Claude AI + MetaTrader 5 (XAUUSD)

An algorithmic trading bot that uses **Claude AI** to analyze multi-timeframe XAUUSD (Gold) charts and automatically execute trades through **MetaTrader 5**.

---

## 📁 Project Structure

```
ai_trade_xauusd/
├── main.py            # Entry point — orchestrates the trading loop
├── config.py          # All settings (risk, symbol, timing, MT5)
├── mt5_connector.py   # MT5 connection, market data, order execution
├── claude_analyst.py  # Claude AI integration — market analysis & signals
├── risk_manager.py    # Risk rules: lot sizing, daily loss limits
├── trade_manager.py   # Converts AI signals into MT5 orders
├── requirements.txt   # Python dependencies
├── .env.example       # Environment variable template
└── logs/              # Auto-created — daily log files
```

---

## ⚙️ Setup

### 1. Prerequisites
- **Windows PC** with MetaTrader 5 installed and logged in
- **Python 3.10+**
- **Anthropic API key** — get at https://console.anthropic.com
- A live or demo **MT5 broker account**

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure credentials
```bash
cp .env.example .env
```
Edit `.env` and fill in:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=YourBroker-Live
```

### 4. Review settings in `config.py`
Key settings to check:
| Setting | Default | Description |
|---------|---------|-------------|
| `LOT_SIZE` | 0.01 | Starting lot size |
| `MAX_LOT_SIZE` | 0.10 | Maximum lot size |
| `STOP_LOSS_PIPS` | 150 | Default stop loss |
| `TAKE_PROFIT_PIPS` | 300 | Default take profit |
| `MAX_RISK_PERCENT` | 1.5% | Risk per trade |
| `MAX_OPEN_TRADES` | 2 | Max simultaneous trades |
| `MIN_CONFIDENCE` | 70% | Claude's minimum confidence to trade |
| `DAILY_LOSS_LIMIT_PCT` | 3.0% | Bot stops if daily loss exceeds this |
| `ANALYSIS_INTERVAL_MINUTES` | 15 | How often Claude analyzes the market |

---

## 🚀 Running the Bot

```bash
python main.py
```

The bot will:
1. Connect to MT5
2. Every 15 minutes, fetch OHLCV data for M5, M15, H1, H4
3. Calculate 10+ technical indicators (EMA, RSI, MACD, BB, ATR, Stoch)
4. Send structured market data to Claude AI
5. Receive a JSON trading decision (BUY / SELL / HOLD / CLOSE)
6. Run risk checks (confidence, margin, daily loss limit, max trades)
7. Execute the trade if approved, with calculated SL/TP

---

## 🧠 How Claude Decides

Claude receives a rich multi-timeframe prompt including:
- Current bid/ask price
- EMA (20/50/200), trend direction
- RSI, Stochastic (momentum)
- MACD (crossover signals)
- Bollinger Bands (volatility & mean reversion)
- ATR (volatility sizing)
- Support & resistance levels
- Recent 5 candles (bull/bear patterns)
- Account balance & open positions

Claude responds with structured JSON:
```json
{
  "action": "buy",
  "confidence": 78,
  "reason": "H1 EMA bullish alignment + RSI recovering from oversold, MACD histogram turning positive",
  "entry_price": 2318.50,
  "stop_loss": 2303.00,
  "take_profit": 2349.00,
  "risk_reward": 2.0,
  "market_bias": "bullish",
  "volatility": "medium",
  "warnings": []
}
```

---

## 🛡️ Risk Management

- ✅ **Confidence gate**: No trade if Claude < 70% confident  
- ✅ **Position limit**: Max 2 simultaneous open trades  
- ✅ **Daily loss limit**: Bot halts if daily loss > 3% of balance  
- ✅ **Dynamic lot sizing**: Based on % account risk + ATR  
- ✅ **Margin check**: Skips trade if margin level < 150%  
- ✅ **Risk:reward gate**: Minimum 1:1.5 R:R required  

---

## ⚠️ Important Warnings

> **Trading involves significant financial risk. Past performance does not guarantee future results.**

- **Start on a DEMO account** before going live
- This bot is for **educational purposes** — always supervise automated trading
- Review Claude's reasoning in the logs before trusting it with real capital
- Ensure your VPS/PC stays online for uninterrupted operation
- The `MetaTrader5` Python package only works on **Windows**

---

## 📊 Logs

Daily logs are saved to `logs/trading_YYYYMMDD.log`.
Each cycle logs: prices, indicators, Claude's decision, risk verdict, and order result.

---

## 🔧 Customization

- **Change symbol**: Set `SYMBOL = "EURUSD"` in `config.py`
- **Change timeframes**: Edit `ANALYSIS_TIMEFRAMES` list
- **Add indicators**: Extend `_add_indicators()` in `mt5_connector.py`
- **Tune Claude prompt**: Edit `SYSTEM_PROMPT` in `claude_analyst.py`
