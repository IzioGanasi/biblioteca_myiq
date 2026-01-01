import asyncio
import json
import sys
import os

# Force usage of local myiq package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from myiq import IQOption

async def test_balances_raw(email, password):
    iq = IQOption(email, password)
    await iq.start()
    
    # Intercepting the raw response from the dispatcher before model conversion
    req_id = "test_balances_req"
    future = iq.dispatcher.create_future(req_id)
    
    await iq.ws.send({
        "name": "sendMessage",
        "request_id": req_id,
        "msg": {
            "name": "internal-billing.get-balances",
            "version": "1.0",
            "body": {"types_ids": [1, 4, 2, 6]}
        }
    })
    
    print("Waiting for balances raw response...")
    raw_response = await future
    
    print("\n--- RAW BALANCES DICTIONARY ---")
    print(json.dumps(raw_response, indent=2))
    
    await iq.close()

if __name__ == "__main__":
    from tests.config import EMAIL, PASSWORD
    asyncio.run(test_balances_raw(EMAIL, PASSWORD))
