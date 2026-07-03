*Read this in other languages: [English](README.md), [Русский](README.ru.md).*

# AI-Driven Async Trading Bot & Streamlit Analytics Dashboard

A high-performance asynchronous Python trading bot that combines technical market analysis with end-to-end filtering of fundamental news noise using local and cloud-based Large Language Models (LLMs). The project includes an interactive web dashboard for real-time equity and log monitoring.

⚠️ **Important Security Note:** This repository contains only the architectural framework (infrastructure), the asynchronous data collection engine, and the web interface. Production AI prompts, proprietary model weights, and precise risk management mathematical formulas are completely isolated, moved to a private scope, and added to `.gitignore`. In the public code, the production strategy is replaced with a demonstration mock class.

## 🚀 Key Technological Features of the Engine

### 1. Asynchronous Core and Fault-Tolerant Parsing
* **Asyncio & HTTPX:** The engine is built on non-blocking requests, providing parallel collection of exchange metrics and end-to-end parsing of news feeds.
* **Network Handling:** Implemented bypass of network restrictions and strict redirect policies for web resources (`follow_redirects=True`).
* **Handling Corrupted Data:** Implemented low-level exception handling when reading data streams, fixing issues with invisible Windows BOM characters by decoding with the `utf-8-sig` encoding.

### 2. Flexible AI Agent Integration (Pluggable AI Layer)
* **LLM Agnostic:** The architecture supports seamless switching between remote APIs (Gemini API) and locally deployed LLM runtimes via LM Studio API servers (Qwen, DeepSeek model families).
* **Response Formatting:** System prompts are designed for strict validation of model responses. The architecture guarantees the generation of valid JSON output from the AI module for safe trading signal parsing by the backend.

### 3. Engineering Risk Management and Capital Protection
* **Margin Management:** Tight control over order parameters and forced leverage fixing at the exchange account level (`Leverage 1x`).
* **Honest Backtesting:** When calculating returns, the engine accounts for real trading vulnerabilities: a mandatory exchange commission is included (Taker Fee 0.05%), along with a slippage protection algorithm during high-volatility movements driven by high-importance news.

### 4. Interactive Web Analytics (Streamlit Frontend)
* An interactive UI dashboard using the Streamlit framework has been developed, providing visualization of trading activity without page reloading using `st_autorefresh`.
* Set up stream processing of CSV trade logs and automatic generation of interactive profit charts.

## 📁 Repository Architecture
* `dashboard.py` — Streamlit frontend analytics dashboard.
* `Testnet binance vision AI/` — Bot's working directory.
  * `live_trader.py` — Main engine for trading cycle and logic.
  * `ai_service.py` — Module for LLM integration and JSON response parsing.
  * `news_parser.py` — High-speed news stream parser.
  * `notifier.py` — Asynchronous Telegram notification module for trades and risk management.
