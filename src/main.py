import asyncio
import aiohttp
import json
import time
import os
import logging
from typing import List, Dict, Any
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Backtest Caller Service")

class BacktestCaller:
    def __init__(self):
        self.base_url = "https://btc-signal-generator-production.up.railway.app/signal/next"
        self.results = []
        self.total_calls = 0
        self.successful_calls = 0
        
    async def call_backtest_service(self, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """Call the backtest service once"""
        try:
            async with session.get(self.base_url, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    self.successful_calls += 1
                    return data
                else:
                    logger.warning(f"HTTP error {response.status} from backtest service")
                    return {"error": f"HTTP {response.status}"}
        except asyncio.TimeoutError:
            logger.warning("Timeout calling backtest service")
            return {"error": "Timeout"}
        except Exception as e:
            logger.error(f"Error calling backtest service: {str(e)}")
            return {"error": str(e)}
    
    async def call_multiple_times(self, num_calls: int = 200) -> Dict[str, Any]:
        """Call the backtest service multiple times asynchronously"""
        self.results = []
        self.total_calls = num_calls
        self.successful_calls = 0
        
        logger.info(f"Starting {num_calls} calls to backtest service")
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession() as session:
                tasks = [self.call_backtest_service(session) for _ in range(num_calls)]
                results = await asyncio.gather(*tasks)
                self.results = results
        except Exception as e:
            logger.error(f"Error in call_multiple_times: {str(e)}")
            raise
        
        end_time = time.time()
        logger.info(f"Completed {num_calls} calls in {end_time - start_time:.2f} seconds")
        
        return self.analyze_results(end_time - start_time)
    
    def analyze_results(self, execution_time: float) -> Dict[str, Any]:
        """Analyze the results and calculate profitability metrics"""
        try:
            successful_results = [r for r in self.results if "error" not in r]
            failed_results = [r for r in self.results if "error" in r]
            
            # Extract PNL data from successful calls
            pnl_data = []
            profitable_trades = 0
            total_trades = 0
            
            for result in successful_results:
                if "evaluation" in result:
                    eval_data = result["evaluation"]
                    if eval_data.get("pnl_percent") is not None:
                        pnl_percent = eval_data["pnl_percent"]
                        pnl_data.append(pnl_percent)
                        
                        if eval_data.get("outcome") != "HOLD":
                            total_trades += 1
                            if eval_data.get("profitable") == True:
                                profitable_trades += 1
            
            # Calculate metrics
            if pnl_data:
                total_pnl = sum(pnl_data)
                avg_pnl = total_pnl / len(pnl_data)
                win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
                max_profit = max(pnl_data) if pnl_data else 0
                max_loss = min(pnl_data) if pnl_data else 0
                
                # Calculate Sharpe ratio
                returns_series = pd.Series(pnl_data)
                sharpe_ratio = (returns_series.mean() / returns_series.std()) * np.sqrt(252) if len(returns_series) > 1 and returns_series.std() != 0 else 0
            else:
                total_pnl = avg_pnl = win_rate = max_profit = max_loss = sharpe_ratio = 0
            
            return {
                "summary": {
                    "total_calls": self.total_calls,
                    "successful_calls": self.successful_calls,
                    "failed_calls": len(failed_results),
                    "success_rate": (self.successful_calls / self.total_calls * 100) if self.total_calls > 0 else 0,
                    "execution_time_seconds": round(execution_time, 2),
                    "calls_per_second": round(self.total_calls / execution_time, 2) if execution_time > 0 else 0
                },
                "profitability_analysis": {
                    "total_pnl_percent": round(total_pnl, 4),
                    "average_pnl_percent": round(avg_pnl, 4),
                    "win_rate_percent": round(win_rate, 2),
                    "total_trades_analyzed": total_trades,
                    "profitable_trades": profitable_trades,
                    "max_profit_percent": round(max_profit, 4),
                    "max_loss_percent": round(max_loss, 4),
                    "sharpe_ratio": round(sharpe_ratio, 4),
                    "final_score": self.calculate_final_score(win_rate, avg_pnl, sharpe_ratio)
                },
                "failed_calls_sample": failed_results[:5] if failed_results else "No failed calls"
            }
        except Exception as e:
            logger.error(f"Error in analyze_results: {str(e)}")
            raise
    
    def calculate_final_score(self, win_rate: float, avg_pnl: float, sharpe_ratio: float) -> float:
        """Calculate a final profitability score (0-100)"""
        try:
            win_rate_score = min(win_rate, 100)
            pnl_score = avg_pnl * 10
            sharpe_score = sharpe_ratio * 20
            
            total_score = (win_rate_score * 0.4) + (pnl_score * 0.4) + (sharpe_score * 0.2)
            
            return max(0, min(100, total_score))
        except Exception as e:
            logger.error(f"Error in calculate_final_score: {str(e)}")
            return 0

backtest_caller = BacktestCaller()

@app.get("/")
async def root():
    return {"message": "Backtest Caller Service - Use /run-backtest to start analysis"}

@app.get("/run-backtest")
async def run_backtest(calls: int = 200):
    """Run the backtest analysis with specified number of calls"""
    try:
        logger.info(f"Received request for {calls} calls")
        
        if calls > 1000:
            return JSONResponse(
                status_code=400,
                content={"error": "Maximum 1000 calls allowed to prevent overload"}
            )
        
        results = await backtest_caller.call_multiple_times(calls)
        return results
        
    except Exception as e:
        logger.error(f"Error in run_backtest endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error running backtest: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}

@app.on_event("startup")
async def startup_event():
    logger.info("Application starting up")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down")

@app.get("/test")
async def test_endpoint():
    """Simple test endpoint to verify the app is running"""
    return {"message": "Test successful", "status": "working"}

if __name__ == "__main__":
    import os
    import uvicorn
    
    # Get port from environment variable or default to 8000
    port = int(os.environ.get("PORT", 8000))
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port
    )
