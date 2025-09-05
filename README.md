# Backtest Caller Service

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
