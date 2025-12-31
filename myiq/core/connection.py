
import json
import asyncio
import websockets
import structlog
from myiq.core.constants import IQ_WS_URL

logger = structlog.get_logger()

class WSConnection:
    def __init__(self, dispatcher):
        self.url = IQ_WS_URL
        self.dispatcher = dispatcher
        self.ws = None
        self.is_connected = False
        self.on_message_hook = None

    async def connect(self):
        self.ws = await websockets.connect(self.url)
        self.is_connected = True
        asyncio.create_task(self._loop())
        logger.info("ws_connected")

    async def _loop(self):
        try:
            async for msg in self.ws:
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    logger.error("ws_invalid_json", message=msg)
                    continue
                    
                if self.on_message_hook:
                    try:
                        self.on_message_hook(data)
                    except Exception as e:
                        logger.error("hook_error", error=str(e))
                        
                self.dispatcher.dispatch(data)
        except Exception as e:
            logger.error("ws_loop_error", error=str(e))
        finally:
            self.is_connected = False
            logger.warning("ws_connection_closed")

    async def send(self, data: dict):
        if not self.is_connected or not self.ws:
            raise ConnectionError("WS not connected")
        await self.ws.send(json.dumps(data))
