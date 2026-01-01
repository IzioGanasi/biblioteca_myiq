import asyncio
import json
import sys
import os

# Force usage of local myiq package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from myiq import IQOption

async def test_candles_raw(email, password):
    iq = IQOption(email, password)
    await iq.start()
    
    active_id = 76 # EUR/USD Blitz
    duration = 60 # 1 minute
    
    req_id = "test_candles_req"
    future = iq.dispatcher.create_future(req_id)
    
    # Raw request for 5 candles
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
                "count": 5
            }
        }
    })
    
    raw_response = await future
    print("\n--- RAW CANDLES DICTIONARY ---")
    print(json.dumps(raw_response, indent=2))
    
    await iq.close()

if __name__ == "__main__":
    from tests.config import EMAIL, PASSWORD
    asyncio.run(test_candles_raw(EMAIL, PASSWORD))
