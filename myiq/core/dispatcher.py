
import asyncio
import structlog
from typing import Dict, List, Callable

logger = structlog.get_logger()

class Dispatcher:
    def __init__(self):
        self._futures: Dict[str, asyncio.Future] = {}
        self._listeners: Dict[str, List[Callable]] = {}

    def create_future(self, request_id: str) -> asyncio.Future:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._futures[request_id] = future
        return future

    def add_listener(self, event_name: str, callback: Callable):
        if event_name not in self._listeners:
            self._listeners[event_name] = []
        self._listeners[event_name].append(callback)

    def remove_listener(self, event_name: str, callback: Callable):
        if event_name in self._listeners:
            if callback in self._listeners[event_name]:
                self._listeners[event_name].remove(callback)

    def dispatch(self, message: dict):
        """Dispatches a message to the appropriate handlers."""
        name = message.get("name")
        # print(f"[DEBUG-DISPATCH] Recebido: {name}") # Descomente para ver tudo
        
        if name == "initialization-data":
            # logger.debug("init_data_received")
            pass

        if not name:
            return

        req_id = str(message.get("request_id", ""))

        # 1. Tratamento de Futures (Request/Response)
        if req_id in self._futures:
            future = self._futures.pop(req_id)
            if not future.done():
                future.set_result(message)

        # 2. Tratamento de Listeners
        if name and name in self._listeners:
            for cb in self._listeners[name]:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        asyncio.create_task(cb(message))
                    else:
                        cb(message)
                except Exception as e:
                    logger.error("listener_error", event_name=name, error=str(e))
        
        # 3. Tratamento Especial: Un-wrap 'sendMessage'
        # Algumas mensagens de evento vêm envelopadas, ex: {"name": "sendMessage", "msg": {"name": "set-user-settings", ...}}
        if name == "sendMessage":
            inner_msg = message.get("msg")
            if isinstance(inner_msg, dict):
                # Repassa o payload interno recursivamente
                self.dispatch(inner_msg)
