# TradingAgents A-share Web Console

This fork adds a local web console for mainland China A-share research.

## What changed

- Local web dashboard under `web/`, with a Windows launcher: `start_tradingagents_web.cmd`.
- A-share-only web workflow. Non-A-share tickers such as `MU.O` or `AAPL` are rejected before the run starts.
- A-share market data through East Money.
- A-share capital-flow data through East Money main-force / order-size flow.
- A-share sentiment and company news through East Money Guba desktop/mobile, with 10jqka used only as an auxiliary public-page snapshot when stable text is available.
- A-share fundamentals through East Money F10 company profile and key financial indicators.
- China RMB government-bond yield curve through the public ChinaBond web endpoint.
- China macro context through the ChinaBond web source, with local data-gap notes when the public page is unavailable.
- Tushare Pro is optional and disabled for news by default because its news APIs require paid permissions.
- Each run can be downloaded as a Word `.docx` report from the web UI.

## Local setup

1. Create a Python virtual environment and install the package dependencies.
2. Install the web dependencies:

```powershell
cd web
npm install
```

3. Copy `.env.example` to `.env` and fill only the keys you use.

```env
DEEPSEEK_API_KEY=
TUSHARE_TOKEN=
TRADINGAGENTS_DATA_VENDOR_CHAIN=eastmoney
TRADINGAGENTS_CAPITAL_FLOW_VENDOR=eastmoney
TRADINGAGENTS_MACRO_VENDOR_CHAIN=chinabond_web,local_note
TRADINGAGENTS_ENABLE_TUSHARE_NEWS=0
TRADINGAGENTS_ENABLE_TUSHARE_MACRO=0
```

4. Start the local web console:

```powershell
.\start_tradingagents_web.cmd
```

The web UI runs locally and does not require committing `.env`. Keep `.env` private.
