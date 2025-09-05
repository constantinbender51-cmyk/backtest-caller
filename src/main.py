import asyncio
import aiohttp
import time
import logging
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
        
    async def call_backtest_service(self, session: aiohttp.ClientSession) -> dict:
        """Call the backtest service once"""
        try:
            async with session.get(self.base_url, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                return {"error": f"HTTP {response.status}"}
        except asyncio.TimeoutError:
            return {"error": "Timeout"}
        except Exception as e:
            return {"error": str(e)}
    
    async def call_multiple_times(self, num_calls: int = 200) -> dict:
        """Call the backtest service multiple times with concurrency"""
        results = []
        successful_calls = 0
        
        logger.info(f"Starting {num_calls} calls to backtest service")
        start_time = time.time()
        
        # Use connection pooling with reasonable limits
        connector = aiohttp.TCPConnector(limit=20, limit_per_host=10)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Process in batches to avoid overwhelming the API
            batch_size = 50
            for batch_start in range(0, num_calls, batch_size):
                batch_end = min(batch_start + batch_size, num_calls)
                batch_tasks = []
                
                for i in range(batch_start, batch_end):
                    batch_tasks.append(self.call_backtest_service(session))
                
                batch_results = await asyncio.gather(*batch_tasks)
                results.extend(batch_results)
                
                # Count successful calls
                successful_in_batch = sum(1 for r in batch_results if isinstance(r, dict) and "error" not in r)
                successful_calls += successful_in_batch
                
                # Log progress
                progress = len(results)
                logger.info(f"Progress: {progress}/{num_calls} calls completed ({successful_in_batch} successful in batch)")
                
                # Small delay between batches to be gentle on the API
                if progress < num_calls:
                    await asyncio.sleep(0.5)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        logger.info(f"Completed {successful_calls}/{num_calls} successful calls in {execution_time:.2f}s")
        
        return self.analyze_results(results, successful_calls, num_calls, execution_time)
    
    def analyze_results(self, results: list, successful_calls: int, total_calls: int, execution_time: float) -> dict:
        """Analyze results and calculate all metrics"""
        successful_results = [r for r in results if isinstance(r, dict) and "error" not in r]
        failed_results = [r for r in results if not isinstance(r, dict) or "error" in r]
        
        # Extract PNL data and trade metrics
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
        
        # Calculate all metrics
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
                "total_calls": total_calls,
                "successful_calls": successful_calls,
                "failed_calls": len(failed_results),
                "success_rate": round((successful_calls / total_calls * 100), 2) if total_calls > 0 else 0,
                "execution_time_seconds": round(execution_time, 2),
                "calls_per_second": round(total_calls / execution_time, 2) if execution_time > 0 else 0
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
    
    def calculate_final_score(self, win_rate: float, avg_pnl: float, sharpe_ratio: float) -> float:
        """Calculate a final profitability score (0-100)"""
        try:
            # Weighted scoring system
            win_rate_score = min(win_rate, 100)  # Max 100 points for win rate
            pnl_score = avg_pnl * 10  # Scale PNL appropriately
            sharpe_score = sharpe_ratio * 20  # Scale Sharpe ratio
            
            # Apply weights
            total_score = (win_rate_score * 0.4) + (pnl_score * 0.4) + (sharpe_score * 0.2)
            
            # Normalize to 0-100 scale
            return max(0, min(100, total_score))
        except Exception:
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
        logger.error(f"Error running backtest: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error running backtest: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}

@app.get("/test")
async def test_endpoint():
    """Test endpoint to verify service is working"""
    return {"message": "Service is working", "status": "ok"}

# For Railway deployment
if __name__ == "__main__":
    import os
    import uvicorn
    
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
