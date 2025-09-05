import asyncio
import aiohttp
import time
import logging
import random
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
        
    async def call_backtest_service(self, session: aiohttp.ClientSession, max_retries: int = 3) -> dict:
        """Call the backtest service with retries"""
        for attempt in range(max_retries):
            try:
                async with session.get(self.base_url, timeout=15) as response:  # Reduced timeout
                    if response.status == 200:
                        data = await response.json()
                        return data
                    elif response.status == 429:  # Rate limited
                        wait_time = (attempt + 1) * 2  # Exponential backoff
                        logger.warning(f"Rate limited, waiting {wait_time}s (attempt {attempt + 1})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        return {"error": f"HTTP {response.status}"}
            except asyncio.TimeoutError:
                logger.warning(f"Timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)  # Wait before retry
                continue
            except Exception as e:
                logger.warning(f"Error on attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                continue
        
        return {"error": "All retries failed"}
    
    async def call_multiple_times(self, num_calls: int = 200) -> dict:
        """Call the backtest service with careful pacing"""
        results = []
        successful_calls = 0
        
        logger.info(f"Starting {num_calls} calls to backtest service")
        start_time = time.time()
        
        # Use very conservative connection limits
        connector = aiohttp.TCPConnector(limit=5, limit_per_host=3)  # Reduced from 20/10
        async with aiohttp.ClientSession(connector=connector) as session:
            # Process in much smaller batches with longer delays
            batch_size = 10  # Reduced from 50
            for batch_start in range(0, num_calls, batch_size):
                batch_end = min(batch_start + batch_size, num_calls)
                batch_tasks = []
                
                for i in range(batch_start, batch_end):
                    batch_tasks.append(self.call_backtest_service(session, max_retries=2))  # Reduced retries
                
                batch_results = await asyncio.gather(*batch_tasks)
                results.extend(batch_results)
                
                # Count successful calls
                successful_in_batch = sum(1 for r in batch_results if isinstance(r, dict) and "error" not in r)
                successful_calls += successful_in_batch
                
                # Log progress
                progress = len(results)
                logger.info(f"Progress: {progress}/{num_calls} calls ({successful_in_batch}/10 successful in batch)")
                
                # Longer delay between batches with jitter
                if progress < num_calls:
                    delay = random.uniform(2.0, 4.0)  # 2-4 second delay between batches
                    logger.info(f"Waiting {delay:.1f}s before next batch...")
                    await asyncio.sleep(delay)
        
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
            "failed_calls_sample": failed_results[:5] if failed_results else "No failed calls",
            "recommendation": "Consider running fewer calls with slower pacing for better success rate" if len(failed_results) > total_calls * 0.3 else "Good success rate"
        }
    
    def calculate_final_score(self, win_rate: float, avg_pnl: float, sharpe_ratio: float) -> float:
        """Calculate a final profitability score (0-100)"""
        try:
            win_rate_score = min(win_rate, 100)
            pnl_score = avg_pnl * 10
            sharpe_score = sharpe_ratio * 20
            
            total_score = (win_rate_score * 0.4) + (pnl_score * 0.4) + (sharpe_score * 0.2)
            
            return max(0, min(100, round(total_score, 2)))
        except Exception:
            return 0

backtest_caller = BacktestCaller()

@app.get("/")
async def root():
    return {"message": "Backtest Caller Service - Use /run-backtest?calls=200 for better success rate"}

@app.get("/run-backtest")
async def run_backtest(calls: int = 200):
    """Run the backtest analysis with specified number of calls"""
    try:
        logger.info(f"Received request for {calls} calls")
        
        if calls > 500:  # Reduced from 1000
            return JSONResponse(
                status_code=400,
                content={"error": "Maximum 500 calls allowed to avoid overwhelming the service"}
            )
        
        results = await backtest_caller.call_multiple_times(calls)
        return results
        
    except Exception as e:
        logger.error(f"Error running backtest: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error running backtest: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}

@app.get("/test-small")
async def test_small():
    """Test with a small number of calls"""
    try:
        results = await backtest_caller.call_multiple_times(10)
        return results
    except Exception as e:
        return {"error": str(e)}

# For Railway deployment
if __name__ == "__main__":
    import os
    import uvicorn
    
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
