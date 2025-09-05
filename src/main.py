import asyncio
import aiohttp
import time
import logging
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
        except Exception as e:
            return {"error": str(e)}
    
    async def call_multiple_times(self, num_calls: int = 200) -> dict:
        """Call the backtest service multiple times with concurrency"""
        results = []
        successful_calls = 0
        pnl_data = []
        
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
                
                # Count successful calls and extract PNL
                for result in batch_results:
                    if isinstance(result, dict) and "error" not in result:
                        successful_calls += 1
                        if "evaluation" in result and result["evaluation"].get("pnl_percent") is not None:
                            pnl_data.append(result["evaluation"]["pnl_percent"])
                
                # Log progress
                progress = len(results)
                logger.info(f"Progress: {progress}/{num_calls} calls completed")
                
                # Small delay between batches to be gentle on the API
                if progress < num_calls:
                    await asyncio.sleep(0.5)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Calculate profitability metrics
        total_pnl = sum(pnl_data) if pnl_data else 0
        avg_pnl = total_pnl / len(pnl_data) if pnl_data else 0
        
        logger.info(f"Completed {successful_calls}/{num_calls} calls in {execution_time:.2f}s")
        
        return {
            "summary": {
                "total_calls": num_calls,
                "successful_calls": successful_calls,
                "failed_calls": num_calls - successful_calls,
                "success_rate": round((successful_calls / num_calls) * 100, 2) if num_calls > 0 else 0,
                "execution_time_seconds": round(execution_time, 2),
                "calls_per_second": round(num_calls / execution_time, 2) if execution_time > 0 else 0
            },
            "profitability_analysis": {
                "total_pnl_percent": round(total_pnl, 4),
                "average_pnl_percent": round(avg_pnl, 4),
                "total_trades_analyzed": len(pnl_data),
                "final_score": self.calculate_score(avg_pnl, successful_calls, num_calls)
            }
        }
    
    def calculate_score(self, avg_pnl: float, successful: int, total: int) -> float:
        """Calculate a simple profitability score"""
        success_rate = (successful / total) * 100 if total > 0 else 0
        score = (success_rate * 0.5) + (avg_pnl * 10 * 0.5)
        return round(min(100, max(0, score)), 2)

backtest_caller = BacktestCaller()

@app.get("/")
async def root():
    return {"message": "Backtest Caller Service - Use /run-backtest?calls=1000 to start analysis"}

@app.get("/run-backtest")
async def run_backtest(calls: int = 200):
    """Run the backtest analysis with specified number of calls"""
    try:
        logger.info(f"Received request for {calls} calls")
        
        if calls > 1000:
            return JSONResponse(
                status_code=400,
                content={"error": "Maximum 1000 calls allowed"}
            )
        
        results = await backtest_caller.call_multiple_times(calls)
        return results
        
    except Exception as e:
        logger.error(f"Error running backtest: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

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
