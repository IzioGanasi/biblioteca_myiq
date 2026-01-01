import asyncio
import json
import sys
import os

# Force usage of local myiq package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from myiq import IQOption

async def test_fetcher_raw(email, password):
    iq = IQOption(email, password)
    await iq.start()
    
    # We want to see how fetch_candles makes multiple requests
    # and what the raw output of each request looks like.
    # We can use the fetch_all_candles function directly to see the batches.
    from myiq.core.candle_fetcher import fetch_all_candles
    
    active_id = 76
    duration = 60
    total_count = 1500 # This will force 2 batches (1000 + 500)
    
    print(f"Fetching {total_count} candles in batches...")
    
    # We can't easily see the raw batches from fetch_candles without modifying it,
    # but we can simulate the process here to show the raw data.
    collected_raw = []
    
    async def get_raw_batch(count):
        req_id = f"fetch_batch_{count}"
        future = iq.dispatcher.create_future(req_id)
        await iq.ws.send({
            "name": "sendMessage",
            "request_id": req_id,
            "msg": {
                "name": "get-candles",
                "version": "2.0",
                "body": {
                    "active_id": active_id,
                    "size": duration,
                    "to": iq.get_server_timestamp(),
                    "count": count
                }
            }
        })
        return await future

    print("--- RAW BATCH 1 (1000 candles) ---")
    batch1 = await get_raw_batch(1000)
    print(f"Batch 1 key count: {len(batch1.get('msg', {}).get('candles', []))}")
    
    print("\n--- RAW BATCH 2 (500 candles) ---")
    batch2 = await get_raw_batch(500)
    print(f"Batch 2 key count: {len(batch2.get('msg', {}).get('candles', []))}")
    
    await iq.close()

if __name__ == "__main__":
    from tests.config import EMAIL, PASSWORD
    asyncio.run(test_fetcher_raw(EMAIL, PASSWORD))
