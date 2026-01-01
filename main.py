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
    candles = await iq.fetch_candles(active_id=2323, duration=60, total=1500)
    print(f"[candles] Received {len(candles)} candles")

    # ----- buy_blitz (trade execution) -----
    # Uncomment the line below to place a real trade (requires a selected balance)
    # result = await iq.buy_blitz(active_id=2323, direction="call", amount=1.0)
    # print("[buy_blitz]", result)

    # ----- get_actives (Explorer) -----
    actives = await iq.get_actives("turbo")
    open_actives = [k for k, v in actives.items() if v['open']]
    print(f"[get_actives] Blitz actives open: {len(open_actives)}")

    # Close the websocket when done
    await iq.close()

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
    await iq.start_candles_stream(active_id=2323, duration=60, callback=lambda d: None)

    # Keep the loop alive briefly to receive a few messages
    await asyncio.sleep(5)
    await iq.close()

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
# 6. Asset Cache (New)
# ---------------------------------------------------------------------------
async def demo_cache(email: str, password: str):
    iq = IQOption(email, password)
    await iq.start()
    
    print("[cache] Waiting for cache to populate...")
    await asyncio.sleep(3) # Give it some time to receive the list
    
    # Example access: Check if asset 76 (EURUSD) is available in BLITZ (Priority) or TURBO
    asset_id = "76"
    
    # 1. Smart Access (Recommended)
    print(f"\n[cache] Consulta Inteligente para ID {asset_id} (Prioridade):")
    smart_info = iq.check_active(asset_id)
    if smart_info:
        print(f"  -> Encontrado em: {smart_info.get('active_type')}")
        print(f"  -> Aberto: {iq.is_active_open(asset_id)}")
    else:
        print("  -> Não encontrado no Smart Cache.")

    # 2. Raw Access (Debug)
    blitz_cache = iq.actives_cache.get("blitz", {})
    info_blitz = blitz_cache.get(asset_id)
    
    if info_blitz:
        print(f"\n[cache] Asset {asset_id} found specifically in BLITZ!")
        print(f"  -> Enabled: {info_blitz.get('enabled')}")
        print(f"  -> Suspended: {info_blitz.get('is_suspended')}")
    else:
        print(f"\n[cache] Asset {asset_id} NOT found in BLITZ specific cache.")
        
    total = sum(len(v) for v in iq.actives_cache.values())
    print(f"[cache] Total actives cached (across all types): {total}")
    await iq.close()

# ---------------------------------------------------------------------------
# 7. User Data (New) - Profile, Settings, Features
# ---------------------------------------------------------------------------
async def demo_user_data(email: str, password: str):
    iq = IQOption(email, password)
    await iq.start()
    
    print("[user] Waiting for profile/settings to sync...")
    await asyncio.sleep(5) 
    
    # 1. Profile
    if iq.profile:
        print(f"[user] Name: {iq.profile.get('name')}")
        print(f"[user] Country ID: {iq.profile.get('country_id')}")
        print(f"[user] City: {iq.profile.get('city')}")
    else:
        print("[user] Profile data not yet received.")

    # 2. Features
    blitz_feat = iq.features.get("blitz-option", "unknown")
    print(f"[user] Feature 'blitz-option': {blitz_feat}")

    # 3. Settings (Last amounts, interface settings)
    trading_conf = iq.user_settings.get("traderoom_gl_trading", {})
    if trading_conf:
        print(f"[user] Last Turbo Bet: {trading_conf.get('lastAmounts', {}).get('turbo')}")
        print(f"[user] Buy One Click Blitz: {trading_conf.get('isBuyOneClickBlitz')}")

    await iq.close()

# ---------------------------------------------------------------------------
# 8. Financial Info (New) - GraphQL
# ---------------------------------------------------------------------------
async def demo_financial_info(email: str, password: str):
    iq = IQOption(email, password)
    await iq.start()
    
    # Example: Ondo (OTC) as per logs, ID 2276
    active_id = 2276 
    print(f"[fin-info] Requesting for Active {active_id} (Ondo)...")
    
    data = await iq.get_financial_info(active_id)
    
    if data:
        print(f"[fin-info] Name: {data.get('name')}")
        print(f"[fin-info] Ticker: {data.get('ticker')}")
        
        # Access nested description
        desc = data.get('fininfo', {}).get('description')
        if desc:
            print(f"[fin-info] Description: {desc[:100]}...") # Truncated
            
        charts = data.get('charts', {})
        if charts:
            print(f"[fin-info] 1Y Change: {charts.get('y1', {}).get('change')}%")
    else:
        print("[fin-info] No data returned (timeout or error).")

    await iq.close()

# ---------------------------------------------------------------------------
# Run demos (replace with your credentials)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Use environment variables or local config for credentials
    # Create a tests/config.py file or set env vars for security
    try:
        from tests.config import EMAIL, PASSWORD
    except ImportError:
        import os
        EMAIL = os.getenv("IQ_EMAIL", "email@example.com")
        PASSWORD = os.getenv("IQ_PASSWORD", "password")

    print(f"Using email: {EMAIL} (masked password)")
    
    if EMAIL == "email@example.com":
         print("Please configure your credentials in tests/config.py or environment variables.")
    else:
        asyncio.run(demo_auth(EMAIL, PASSWORD))
        asyncio.run(demo_iqoption(EMAIL, PASSWORD))
        demo_utils()
        asyncio.run(demo_dispatcher(EMAIL, PASSWORD))
        demo_models()
        asyncio.run(demo_cache(EMAIL, PASSWORD))
        asyncio.run(demo_user_data(EMAIL, PASSWORD))
        asyncio.run(demo_financial_info(EMAIL, PASSWORD))
