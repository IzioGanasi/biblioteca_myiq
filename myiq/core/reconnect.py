import asyncio
import structlog
from myiq.core.connection import WSConnection
from myiq.core.dispatcher import Dispatcher

logger = structlog.get_logger()

class ReconnectingWS:
    """Wraps :class:`WSConnection` and automatically reconnects on failures.

    The wrapper mimics the original ``WSConnection`` API (``send`` and
    ``on_message_hook``) so existing client code does not need to change.
    """

    def __init__(self, dispatcher: Dispatcher, url: str, max_retries: int = 5, backoff: float = 1.0):
        self.url = url
        self.dispatcher = dispatcher
        self.max_retries = max_retries
        self.backoff = backoff
        self.ws: WSConnection | None = None
        self._on_message_hook = None
        self.on_reconnect = None # Callback for reconnection events
        self._connected = asyncio.Event()

    @property
    def on_message_hook(self):
        return self._on_message_hook

    @on_message_hook.setter
    def on_message_hook(self, fn):
        self._on_message_hook = fn
        if self.ws:
            self.ws.on_message_hook = fn

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set() and self.ws and self.ws.is_connected

    async def connect(self):
        await self._attempt_connect()
        # start background monitor that watches for disconnections
        asyncio.create_task(self._monitor())

    async def _attempt_connect(self):
        for attempt in range(1, self.max_retries + 1):
            try:
                self.ws = WSConnection(self.dispatcher)
                self.ws.on_message_hook = self._on_message_hook
                await self.ws.connect()
                self._connected.set()
                logger.info("ws_connected", attempt=attempt)
                return
            except Exception as exc:
                logger.error("ws_connect_error", attempt=attempt, error=str(exc))
                await asyncio.sleep(self.backoff * attempt)
        raise ConnectionError("Unable to reconnect after several attempts")

    async def send(self, data: dict):
        await self._connected.wait()
        return await self.ws.send(data)

    async def _monitor(self):
        """Continuously monitor the underlying connection and reconnect if it drops."""
        while self._connected.is_set() or self.ws:
            await asyncio.sleep(1)
            # If explicitely closed, stop monitoring
            if not self._connected.is_set() and self.ws is None:
                break
                
            if self.ws is None or not getattr(self.ws, "is_connected", False):
                if not self._connected.is_set() and self.ws: # Was connected, now lost
                     # Double check if user didn't request close
                     pass

                logger.warning("ws_lost", reason="disconnected")
                self._connected.clear()
                try:
                    await self._attempt_connect()
                    # Trigger Reconnect Callback if set
                    if hasattr(self, "on_reconnect") and self.on_reconnect:
                        if asyncio.iscoroutinefunction(self.on_reconnect):
                            await self.on_reconnect()
                        else:
                            self.on_reconnect()
                except:
                    break

    async def close(self):
        self._connected.clear()
        if self.ws:
            await self.ws.close()
            self.ws = None
