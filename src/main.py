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
                    return await response.json()
                return {"error": f"HTTP {response.status}"}
        except Exception as e:
            return {"error": str(e)}
    
    async def call_multiple_times(self, num_calls: int = 200) -> dict:
        """Call the backtest service multiple times"""
        results = []
        successful_calls = 0
        
        logger.info(f"Starting {num_calls} calls")
        start_time = time.time()
        
        # Use connection pooling with limits
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = []
            for i in range(num_calls):
                task = self.call_backtest_service(session)
                tasks.append(task)
                
                # Process in smaller batches to avoid timeouts
                if len(tasks) >= 50 or i == num_calls - 1:
                    batch_results = await asyncio.gather(*tasks)
                    results.extend(batch_results)
                    tasks = []
                    
                    # Log progress
                    logger.info(f"Progress: {len(results)}/{num_calls} calls completed")
                    
                    # Small delay between batches
                    await asyncio.sleep(0.1)
        
        end_time = time.time()
        
        # Count successful calls
        successful_calls = sum(1 for r in results if "error" not in r)
        
        logger.info(f"Completed {successful_calls}/{num_calls} successful calls in {end_time - start_time:.2f}s")
        
        return {
            "total_calls": num_calls,
            "successful_calls": successful_calls,
            "failed_calls": num_calls - successful_calls,
            "execution_time": round(end_time - start_time, 2),
            "sample_result": results[0] if results else "No results"
        }

backtest_caller = BacktestCaller()

@app.get("/")
async def root():
    return {"message": "Backtest Caller Service - Use /run-backtest to start analysis"}

@app.get("/run-backtest")
async def run_backtest(calls: int = 200):
    """Run the backtest analysis"""
    try:
        logger.info(f"Starting backtest with {calls} calls")
        results = await backtest_caller.call_multiple_times(calls)
        return results
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}

@app.get("/test")
async def test_endpoint():
    """Simple test endpoint"""
    return {"message": "Test successful", "status": "working"}

# For local testing
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
