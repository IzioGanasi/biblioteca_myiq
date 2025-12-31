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
        self._connected = asyncio.Event()

    @property
    def on_message_hook(self):
        return self._on_message_hook

    @on_message_hook.setter
    def on_message_hook(self, fn):
        self._on_message_hook = fn
        if self.ws:
            self.ws.on_message_hook = fn

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
        while True:
            await asyncio.sleep(1)
            if self.ws is None or not getattr(self.ws, "is_connected", False):
                logger.warning("ws_lost", reason="disconnected")
                self._connected.clear()
                await self._attempt_connect()
