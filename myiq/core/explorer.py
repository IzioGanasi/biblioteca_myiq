import asyncio
import structlog
from typing import Dict, Any

logger = structlog.get_logger()

async def get_initialization_data_raw(iq_client, timeout: float = 30.0, retries: int = 3) -> Dict[str, Any]:
    """
    Sends 'get-initialization-data' and waits for the response.
    This contains information about all available assets, their schedules, and status.
    Includes retry logic to handle timeouts or connection drops.
    """
    req_id = "fetch_init_data"
    
    for attempt in range(1, retries + 1):
        init_future = asyncio.get_running_loop().create_future()
        
        def on_init(msg):
            if msg.get("name") == "initialization-data":
                if not init_future.done():
                    init_future.set_result(msg)
                    
        iq_client.dispatcher.add_listener("initialization-data", on_init)
        
        try:
            logger.info("fetching_init_data", attempt=attempt, max_retries=retries)
            await iq_client.ws.send({
                "name": "sendMessage",
                "request_id": req_id,
                "msg": {
                    "name": "get-initialization-data",
                    "version": "4.0",
                    "body": {}
                }
            })
            
            # Wait for response with timeout
            raw_res = await asyncio.wait_for(init_future, timeout=timeout)
            return raw_res.get("msg", {})
            
        except asyncio.TimeoutError:
            logger.warning("init_data_timeout", attempt=attempt)
            if attempt == retries:
                logger.error("init_data_failed_all_attempts")
                raise TimeoutError(f"Falha ao obter dados de inicialização após {retries} tentativas. Verifique sua conexão.")
        except Exception as e:
            logger.error("init_data_error", attempt=attempt, error=str(e))
            if attempt == retries:
                raise
            await asyncio.sleep(1) # Wait a bit before retry on generic error
        finally:
            iq_client.dispatcher.remove_listener("initialization-data", on_init)
    
    return {}

def is_market_open(schedule: list, current_time: int) -> bool:
    """Checks if current time is within any of the open intervals."""
    if not schedule:
        return False
    for start, end in schedule:
        if start <= current_time <= end:
            return True
    return False

async def get_all_actives_status(iq_client, instrument_type: str = "turbo") -> Dict[int, Dict[str, Any]]:
    """
    Extracts actives status from initialization data.
    Categories: 'turbo', 'binary', 'digital'
    """
    data = await get_initialization_data_raw(iq_client)
    server_time = iq_client.get_server_timestamp()
    
    category_data = data.get(instrument_type, {})
    actives_dict = category_data.get("actives", {})
    
    results = {}
    for active_id, info in actives_dict.items():
        is_enabled = info.get("enabled", False)
        is_suspended = info.get("is_suspended", False)
        schedule = info.get("schedule", [])
        
        # Check if currently in an open window
        market_open = is_market_open(schedule, server_time)
        
        # Profit Calculation (100 - commission)
        # Note: Structure seems to be option -> profit -> commission
        commission = info.get("option", {}).get("profit", {}).get("commission", 0)
        profit_percent = 100 - commission if commission > 0 else 0

        # Detailed Status
        results[int(active_id)] = {
            "name": info.get("name"),
            "ticker": info.get("ticker"),
            "enabled": is_enabled,
            "suspended": is_suspended,
            "market_open": market_open,
            "is_open": is_enabled and not is_suspended and market_open,
            "profit_percent": profit_percent,
            "image": info.get("image"),
            "schedule": schedule
        }
        
    return results
