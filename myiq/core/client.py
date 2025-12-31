
import asyncio
import time
import structlog
from typing import List, Optional, Callable
from myiq.http.auth import IQAuth
from myiq.core.reconnect import ReconnectingWS
from myiq.core.dispatcher import Dispatcher
from myiq.core.utils import get_req_id, get_sub_id, get_client_id
from myiq.core.constants import *
from myiq.models.base import WsRequest, WsMessageBody, Balance, Candle

logger = structlog.get_logger()

class IQOption:
    def __init__(self, email: str, password: str):
        self.auth = IQAuth(email, password)
        self.dispatcher = Dispatcher()
        self.ws = ReconnectingWS(self.dispatcher, IQ_WS_URL)
        self.ssid = None
        self.active_balance_id = None
        self.server_time_offset = 0

    async def start(self):
        self.ssid = await self.auth.get_ssid()
        if not self.ssid:
            raise ValueError("Falha na autenticação HTTP: SSID não obtido. Verifique suas credenciais.")
        
        self.ws.on_message_hook = self._on_ws_message
        logger.info("connecting_ws")
        await self.ws.connect()
        
        logger.info("authenticating_ws")
        auth_success = await self._authenticate()
        if not auth_success:
            raise ConnectionError("Falha na autenticação via WebSocket.")
            
        await self.subscribe_portfolio()

    def _on_ws_message(self, msg: dict):
        if msg.get("name") == EV_TIME_SYNC:
            server_ts = msg.get("msg")
            local_ts = time.time() * 1000
            self.server_time_offset = server_ts - local_ts

    def get_server_timestamp(self) -> int:
        return int((time.time() * 1000 + self.server_time_offset) / 1000)

    async def _authenticate(self) -> bool:
        req_id = get_req_id()
        future = self.dispatcher.create_future(req_id)
        
        # We also listen for the "authenticated" event directly just in case req_id is missing
        auth_event_future = asyncio.get_running_loop().create_future()
        def on_auth_msg(msg):
            if msg.get("name") == EV_AUTHENTICATED:
                if not auth_event_future.done():
                    auth_event_future.set_result(msg)
        
        self.dispatcher.add_listener(EV_AUTHENTICATED, on_auth_msg)
        
        await self.ws.send({
            "name": OP_AUTHENTICATE,
            "request_id": req_id,
            "msg": {"ssid": self.ssid, "protocol": 3}
        })
        
        try:
            # Wait for either the request-specific response or the global authenticated event
            done, pending = await asyncio.wait(
                [future, auth_event_future], 
                return_when=asyncio.FIRST_COMPLETED,
                timeout=10.0
            )
            
            for p in pending: p.cancel()
            
            if not done:
                logger.error("auth_timeout")
                return False
                
            res = list(done)[0].result()
            
            # Check if it's an error message
            if res.get("name") == "error" or (res.get("msg") and res["msg"] == "unauthenticated"):
                logger.error("auth_failed", response=res)
                return False
                
            logger.info("authenticated_successfully")
            return True
        finally:
            self.dispatcher.remove_listener(EV_AUTHENTICATED, on_auth_msg)

    async def subscribe_portfolio(self):
        req_ids = [get_sub_id(), get_sub_id()]
        # Ordem alterada
        await self.ws.send({
            "name": "subscribeMessage",
            "request_id": req_ids[0],
            "msg": {"name": "portfolio.order-changed", "version": "2.0", "params": {"routingFilters": {"instrument_type": INSTRUMENT_TYPE_BLITZ}}}
        })
        # Posição alterada (Resultado)
        await self.ws.send({
            "name": "subscribeMessage",
            "request_id": req_ids[1],
            "msg": {"name": "portfolio.position-changed", "version": "3.0", "params": {"routingFilters": {"instrument_type": INSTRUMENT_TYPE_BLITZ}}}
        })
        logger.info("portfolio_subscribed")

    async def get_balances(self) -> List[Balance]:
        req_id = get_req_id()
        future = self.dispatcher.create_future(req_id)
        payload = WsRequest(name="sendMessage", request_id=req_id, msg=WsMessageBody(name=OP_GET_BALANCES, version="1.0", body={"types_ids": [1, 4, 2, 6]}))
        await self.ws.send(payload.model_dump())
        res = await future
        return [Balance(**b) for b in res.get("msg", [])]

    async def change_balance(self, balance_id: int):
        self.active_balance_id = balance_id
        logger.info("balance_selected", id=balance_id)

    # --- CANDLES STREAM ---
    async def start_candles_stream(self, active_id: int, duration: int, callback: Callable[[dict], None]):
        # 1. Manda configuração de GRID para forçar o servidor a enviar candles
        grid_payload = {
            "name": "traderoom_gl_grid",
            "version": 2,
            "client_id": get_client_id(),
            "config": {
                "name": "default",
                "fixedNumberOfPlotters": 1,
                "plotters": [{
                    "activeId": active_id,
                    "activeType": INSTRUMENT_TYPE_BLITZ,
                    "plotType": "candles",
                    "candleDuration": duration,
                    "isMinimized": False
                }],
                "selectedActiveId": active_id
            }
        }
        await self.ws.send({
            "name": "sendMessage",
            "request_id": get_req_id(),
            "msg": {"name": OP_SET_SETTINGS, "version": "1.0", "body": grid_payload}
        })
        
        # 2. Inscreve no canal também por segurança
        await self.ws.send({
            "name": "subscribeMessage",
            "request_id": get_sub_id(),
            "msg": {
                "name": EV_CANDLE_GENERATED,
                "version": "2.0",
                "params": {"routingFilters": {"active_id": int(active_id), "size": int(duration)}}
            }
        })

        # 3. Listener
        def on_candle(msg):
            if msg.get("name") == EV_CANDLE_GENERATED:
                data = msg.get("msg", {})
                # Validação de string para evitar erro de tipo
                if str(data.get("active_id")) == str(active_id):
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(data))
                    else:
                        callback(data)

        self.dispatcher.add_listener(EV_CANDLE_GENERATED, on_candle)
        logger.info("stream_started", active=active_id)

    async def get_candles(self, active_id: int, duration: int, count: int) -> List[Candle]:
        req_id = get_req_id()
        future = self.dispatcher.create_future(req_id)
        to_time = self.get_server_timestamp()
        body = {"active_id": active_id, "size": duration, "to": to_time, "count": count, "": "1"}
        payload = WsRequest(name="sendMessage", request_id=req_id, msg=WsMessageBody(name=OP_GET_CANDLES, version="2.0", body=body))
        await self.ws.send(payload.model_dump())
        res = await future
        return [Candle(**c) for c in res.get("msg", {}).get("candles", [])]

    # --- TRADING ---
    async def fetch_candles(self, active_id: int, duration: int, total: int) -> list[Candle]:
        """Fetch an arbitrary number of candles, handling the 1000‑candle limit.
        Parameters
        ----------
        active_id: int
            Instrument identifier.
        duration: int
            Candle duration in seconds.
        total: int
            Desired total number of candles.
        """
        from myiq.core.candle_fetcher import fetch_all_candles
        return await fetch_all_candles(self, active_id, duration, total)
    async def buy_blitz(self, active_id: int, direction: str, amount: float, duration: int = 30) -> dict:
        if not self.active_balance_id: raise ValueError("Saldo necessario")
        req_id = get_req_id()
        server_time = self.get_server_timestamp()
        expired = server_time + duration

        body = {
            "user_balance_id": self.active_balance_id,
            "active_id": active_id,
            "option_type_id": OPTION_TYPE_BLITZ,
            "direction": direction.lower(),
            "expired": expired,
            "expiration_size": duration,
            "refund_value": 0,
            "price": float(amount),
            "value": 0, "profit_percent": 85
        }

        payload = WsRequest(name="sendMessage", request_id=req_id, msg=WsMessageBody(name=OP_OPEN_OPTION, version="2.0", body=body))
        
        uuid_future = asyncio.get_running_loop().create_future()
        
        def on_open(msg):
            if msg.get("name") == EV_POSITION_CHANGED:
                raw = msg.get("msg", {})
                if "raw_event" in raw:
                    evt = raw["raw_event"].get("binary_options_option_changed1", {})
                    # Verifica ID e Status Opened
                    if str(evt.get("active_id")) == str(active_id) and evt.get("result") == "opened":
                        if not uuid_future.done():
                            uuid_future.set_result(raw.get("id"))

        self.dispatcher.add_listener(EV_POSITION_CHANGED, on_open)
        logger.info("sending_order")
        await self.ws.send(payload.model_dump())

        try:
            # 1. Espera abrir (Timeout 8s)
            order_uuid = await asyncio.wait_for(uuid_future, timeout=8.0)
            self.dispatcher.remove_listener(EV_POSITION_CHANGED, on_open)
            logger.info("order_opened", uuid=order_uuid)
            
            # 2. Inscreve na ordem específica
            await self.ws.send({
                "name": "sendMessage",
                "request_id": get_req_id(),
                "msg": {
                    "name": OP_SUBSCRIBE_POSITIONS,
                    "version": "1.0",
                    "body": {"frequency": "frequent", "ids": [order_uuid]}
                }
            })

            # 3. Espera resultado
            result_future = asyncio.get_running_loop().create_future()
            def on_result(msg):
                if msg.get("name") == EV_POSITION_CHANGED:
                    raw = msg.get("msg", {})
                    if raw.get("id") == order_uuid:
                        evt = raw.get("raw_event", {}).get("binary_options_option_changed1", {})
                        res_type = evt.get("result") # win/loose/equal
                        if res_type in ["win", "loose", "equal"]:
                            if not result_future.done():
                                profit = evt.get("win_enrolled_amount", 0) - evt.get("amount", 0) if res_type == "win" else -evt.get("amount", 0)
                                result_future.set_result({"status": "completed", "result": res_type, "profit": profit, "pnl": raw.get("pnl", 0)})

            self.dispatcher.add_listener(EV_POSITION_CHANGED, on_result)
            result = await asyncio.wait_for(result_future, timeout=duration + 15)
            self.dispatcher.remove_listener(EV_POSITION_CHANGED, on_result)
            return result
        except asyncio.TimeoutError:
            self.dispatcher.remove_listener(EV_POSITION_CHANGED, on_open)
            return {"status": "error", "result": "timeout", "pnl": 0}
