
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
        try:
            # Aumentamos o timeout para 20 segundos para evitar erros de handshake
            # max_size=None permite mensagens maiores que o padrão (1MB)
            # ping_interval=None desativa o ping automático do websockets (o server da IQ pode não responder a Pings padrão)
            self.ws = await websockets.connect(self.url, open_timeout=20, ping_interval=None, ping_timeout=None, max_size=20 * 1024 * 1024)
            self.is_connected = True
            self._receive_task = asyncio.create_task(self._loop())
            logger.info("websocket_connected")
        except asyncio.TimeoutError:
            logger.error("websocket_timeout")
            self.is_connected = False
            raise ConnectionError("Tempo limite esgotado ao conectar ao WebSocket (Timeout). Verifique sua internet ou se a corretora está acessível.")
        except Exception as e:
            logger.error("websocket_connection_failed", error=str(e))
            self.is_connected = False
            if "gaierror" in str(e):
                 raise ConnectionError("Falha de DNS/Rede (gaierror). Verifique sua conexão com a internet.")
            raise ConnectionError(f"Falha ao conectar no WebSocket: {str(e)}")

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
        except asyncio.CancelledError:
            # Tarefa cancelada (shutdown normal)
            pass
        except Exception as e:
            # Ignora erro comum de fechamento do websockets onde o server não manda frame de volta
            if "sent 1000" in str(e) or "sent 1001" in str(e):
                pass 
            else:
                logger.error("ws_loop_error", error=str(e))
        finally:
            self.is_connected = False
            logger.warning("ws_connection_closed")

    async def send(self, data: dict):
        if not self.is_connected or not self.ws:
            raise ConnectionError("WS not connected")
        await self.ws.send(json.dumps(data))

    async def close(self):
        self.is_connected = False
        if self.ws:
            await self.ws.close()
            self.ws = None
