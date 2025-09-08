> ⚠️ **Clarification**  
> This repository – along with every other “bot” project in the `constantinbender51-cmyk` namespace – is **scrap / legacy code** and should **not** be treated as a working or profitable trading system.  
>  
> The **only** repos that still receive updates and are intended for forward-testing are:  
> - `constantinbender51-cmyk/sigtrabot`  
> - `constantinbender51-cmyk/DeepSeekGenerator-v.-1.4` (a.k.a. “DeepSignal v. 1.4”)  
>  
> Complete list of repos that remain **functionally maintained** (but still **unproven** in live, statistically-significant trading):  
> - `constantinbender51-cmyk/Kraken-futures-API`  
> - `constantinbender51-cmyk/sigtrabot`  
> - `constantinbender51-cmyk/binance-btc-data`  
> - `constantinbender51-cmyk/SigtraConfig`  
> - `constantinbender51-cmyk/Simple-bot-complex-behavior-project-`  
> - `constantinbender51-cmyk/DeepSeekGenerator-v.-1.4`  
>  
> > None of the above has demonstrated **statistically significant profitability** in out-of-sample, live trading; **DeepSignal v. 1.4** is merely **showing early promise** and remains experimental.
> >
> > # Backtest Caller Service

A service that calls the BTC signal generator backtest service multiple times and analyzes profitability.

## Features

- Calls the backtest service asynchronously for efficiency
- Analyzes PNL data and calculates profitability metrics
- Provides a final profitability score (0-100)
- FastAPI-based REST API
- Ready for deployment on Railway

## API Endpoints

- `GET /` - Root endpoint
- `GET /run-backtest?calls=200` - Run backtest analysis (default: 200 calls)
- `GET /health` - Health check

## Deployment on Railway

1. Fork/Create this repository
2. Connect your Railway account to the repository
3. Deploy automatically

## Local Development

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload
