import asyncio
import json
import sys
import os

# Force usage of local myiq package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from myiq import IQOption

async def test_ws_monitor_raw(email, password):
    iq = IQOption(email, password)
    
    # Hook to print EVERY message received
    def raw_monitor(msg):
        print(f"\n--- INCOMING RAW MESSAGE ({msg.get('name')}) ---")
        # Truncate long messages (like option lists) for readability
        content = json.dumps(msg, indent=2)
        if len(content) > 1000:
            print(content[:1000] + "... [TRUNCATED]")
        else:
            print(content)

    iq.ws.on_message_hook = raw_monitor
    
    print("Connecting and starting monitor (Ctrl+C to stop)...")
    await iq.start()
    
    # Stay connected to see events (candles, etc)
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Stopping monitor...")
    finally:
        await iq.close()

if __name__ == "__main__":
    from tests.config import EMAIL, PASSWORD
    asyncio.run(test_ws_monitor_raw(EMAIL, PASSWORD))
