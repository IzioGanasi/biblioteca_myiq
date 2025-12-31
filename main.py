# Example usage of the myiq library

"""This script demonstrates how to use each component of the
`myiq` package, covering **all public methods** of `IQOption`.
It is **not** part of the library itself; it serves as a reference for developers.
"""

import asyncio
from myiq import IQOption, IQAuth, Balance, Candle, get_req_id, get_sub_id, get_client_id

# ---------------------------------------------------------------------------
# 1. Authentication (HTTP) – IQAuth
# ---------------------------------------------------------------------------
async def demo_auth(email: str, password: str):
    auth = IQAuth(email, password)
    ssid = await auth.get_ssid()
    print("[auth] SSID:", ssid)

# ---------------------------------------------------------------------------
# 2. Core client – IQOption (WebSocket wrapper)
# ---------------------------------------------------------------------------
async def demo_iqoption(email: str, password: str):
    iq = IQOption(email, password)
    await iq.start()                     # performs HTTP auth + WS connection

    # ----- get_balances -----
    balances = await iq.get_balances()
    print("[balances]", balances)

    # ----- change_balance (choose first real or practice balance) -----
    if balances:
        await iq.change_balance(balances[0].id)
        print(f"[change_balance] Selected balance id {balances[0].id}")

    # ----- get_server_timestamp (internal but useful) -----
    server_ts = iq.get_server_timestamp()
    print("[server_timestamp]", server_ts)

    # ----- subscribe_portfolio (explicit call – usually done in start) -----
    await iq.subscribe_portfolio()
    print("[subscribe_portfolio] Subscribed to portfolio events")

    # ----- fetch_candles (historical, >1000 possible) -----
    candles = await iq.fetch_candles(active_id=76, duration=60, total=1500)
    print(f"[candles] Received {len(candles)} candles")

    # ----- buy_blitz (trade execution) -----
    # Uncomment the line below to place a real trade (requires a selected balance)
    # result = await iq.buy_blitz(active_id=76, direction="call", amount=1.0)
    # print("[buy_blitz]", result)

    # Close the websocket when done
    await iq.ws.ws.close()

# ---------------------------------------------------------------------------
# 3. Utilities – request / subscription IDs
# ---------------------------------------------------------------------------
def demo_utils():
    print("req_id:", get_req_id())
    print("sub_id:", get_sub_id())
    print("client_id:", get_client_id())

# ---------------------------------------------------------------------------
# 4. Dispatcher – event handling (candle stream example)
# ---------------------------------------------------------------------------
async def demo_dispatcher(email: str, password: str):
    iq = IQOption(email, password)
    await iq.start()

    def on_candle(msg: dict):
        print("[listener] Candle event received:", msg)

    iq.dispatcher.add_listener("candle-generated", on_candle)

    # Start a candle stream (will trigger the listener)
    await iq.start_candles_stream(active_id=76, duration=60, callback=lambda d: None)

    # Keep the loop alive briefly to receive a few messages
    await asyncio.sleep(5)
    await iq.ws.ws.close()

# ---------------------------------------------------------------------------
# 5. Models – Pydantic data structures
# ---------------------------------------------------------------------------
def demo_models():
    raw_balance = {"id": 123, "type": 4, "amount": 100.0, "currency": "USD"}
    balance = Balance(**raw_balance)
    print("[model] Balance instance:", balance)

    raw_candle = {
        "id": 1,
        "from": 1700000000,
        "to": 1700000060,
        "open": 1.1234,
        "close": 1.1240,
        "min": 1.1220,
        "max": 1.1250,
        "volume": 2500.0,
    }
    candle = Candle(**raw_candle)
    print("[model] Candle instance:", candle)

# ---------------------------------------------------------------------------
# Run demos (replace with your credentials)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    EMAIL = "seu_email@exemplo.com"
    PASSWORD = "sua_senha"
    asyncio.run(demo_auth(EMAIL, PASSWORD))
    asyncio.run(demo_iqoption(EMAIL, PASSWORD))
    demo_utils()
    asyncio.run(demo_dispatcher(EMAIL, PASSWORD))
    demo_models()
