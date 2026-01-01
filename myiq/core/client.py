
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
        self.actives_cache = {}

    async def start(self):
        self.ssid = await self.auth.get_ssid()
        
        # Reconexão Automática: Registrar Callback
        self.ws.on_reconnect = self._on_reconnect
        self.ws.on_message_hook = self._on_ws_message
        
        logger.info("connecting_ws")
        await self.ws.connect()
        
        logger.info("authenticating_ws")
        await self._authenticate()
            
        await self.subscribe_portfolio()
        
        # Iniciar Heartbeat
        asyncio.create_task(self._heartbeat_loop())

    def check_connect(self) -> bool:
        """
        Verifica se a conexão WebSocket está ativa e autenticada.
        
        Returns:
            bool: True se conectado e autenticado, False caso contrário.
        """
        if self.ws and self.ws.is_connected and self.ssid:
            return True
        return False

    async def _on_reconnect(self):
        """Called automatically by ReconnectingWS when connection is restored."""
        logger.info("performing_reconnection_tasks")
        try:
            # Re-Autenticar
            await self._authenticate()
            # Re-Inscrever
            await self.subscribe_portfolio()
            logger.info("reconnection_tasks_completed")
        except Exception as e:
            logger.error("reconnection_failed", error=str(e))

    async def _heartbeat_loop(self):
        """Sends periodic heartbeats to keep connection alive."""
        # Loop infinito enquanto a instância client existir (mesmo se ws cair/voltar)
        while True:
            try:
                if self.ws and self.ws.is_connected and self.ssid:
                     await self.ws.send({
                        "name": "ssid", 
                        "request_id": get_req_id(), 
                        "msg": self.ssid
                    })
            except Exception as e:
                logger.debug("heartbeat_error", error=str(e))
            
            await asyncio.sleep(20)

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
                msg_content = res.get("msg")
                raise ConnectionError(f"Falha na autenticação via WebSocket: {msg_content}")
                
            logger.info("authenticated_successfully")
            return True
        finally:
            self.dispatcher.remove_listener(EV_AUTHENTICATED, on_auth_msg)

    async def _send_with_retry(self, name: str, body: dict, version: str = "1.0", timeout: float = 20.0, retries: int = 3) -> dict:
        """Helper to send WsRequests with retry logic."""
        for attempt in range(1, retries + 1):
            req_id = get_req_id()
            future = self.dispatcher.create_future(req_id)
            payload = WsRequest(name="sendMessage", request_id=req_id, msg=WsMessageBody(name=name, version=version, body=body))
            
            try:
                await self.ws.send(payload.model_dump())
                return await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("request_timeout", name=name, attempt=attempt)
                if attempt == retries:
                    raise TimeoutError(f"Request '{name}' timed out after {retries} attempts.")
            except Exception as e:
                logger.error("request_error", name=name, error=str(e), attempt=attempt)
                if attempt == retries: raise
                await asyncio.sleep(0.5)
        return {}

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
        res = await self._send_with_retry(OP_GET_BALANCES, {"types_ids": [1, 4, 2, 6]}, version="1.0")
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
        to_time = self.get_server_timestamp()
        body = {"active_id": active_id, "size": duration, "to": to_time, "count": count, "": "1"}
        res = await self._send_with_retry(OP_GET_CANDLES, body, version="2.0")
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

    async def get_actives(self, instrument_type: str = "turbo") -> dict:
        """
        Returns a dictionary of all actives for the given instrument type.
        Categories: 'turbo', 'binary', 'digital'
        Updates the internal cache.
        """
        from myiq.core.explorer import get_all_actives_status
        actives = await get_all_actives_status(self, instrument_type)
        self.actives_cache.update(actives)
        return actives

    def check_active(self, active_id: int) -> dict:
        """
        Returns the cached status of an active. 
        Returns an empty dict if not found.
        """
        return self.actives_cache.get(int(active_id), {})

    def get_profit_percent(self, active_id: int) -> int:
        """Returns the profit percentage for the active (e.g. 86)."""
        return self.check_active(active_id).get("profit_percent", 0)

    def is_active_open(self, active_id: int) -> bool:
        """Checks if the active is currently open for trading."""
        return self.check_active(active_id).get("is_open", False)

    async def close(self):
        """Close the WebSocket connection."""
        await self.ws.close()
    async def buy_blitz(self, active_id: int, direction: str, amount: float, duration: int = 30) -> dict:
        """
        Executes a Blitz option trade.
        
        Args:
            active_id: Asset ID (e.g. 76 for EURUSD).
            direction: 'call' or 'put'.
            amount: Investment amount.
            duration: Duration in seconds (default 30).
        """
        if not self.active_balance_id:
            raise ValueError("Saldo não selecionado. Use change_balance() primeiro.")

        # 1. Recuperar info do ativo para obter profit_percent correto
        # Precisamos disso pois o servidor valida o payout enviado
        profit_percent = self.get_profit_percent(active_id)
        if profit_percent == 0:
            # Tenta buscar on-the-fly se não tiver no cache
            # (Adicionar um fetch rápido ou usar valor padrão seguro/arriscado)
            # Para segurança, vamos logar aviso e tentar 87% (comum) ou falhar
            logger.warning("payout_not_found_in_cache", active_id=active_id)
            # Ideal seria esperar o explorer, mas vamos assumir que o usuário já carregou a lista
            
        req_id = get_req_id()
        server_time = self.get_server_timestamp()
        if server_time == 0: server_time = int(time.time())

        # Lógica de Expiração (Safety Window)
        # Alinha com o final do PRÓXIMO minuto para garantir janela de compra aberta
        # Blitz geralmente aceita múltiplos de 30s ou 60s alinhados
        # O log de sucesso mostrou expiração em :00 ou :30
        # Vamos usar a lógica (M+2) que funcionou nos testes manuais
        expired = (server_time - (server_time % 60)) + 120
        
        body = {
            "user_balance_id": self.active_balance_id,
            "active_id": active_id,
            "option_type_id": OPTION_TYPE_BLITZ, # 12
            "direction": direction.lower(),
            "expired": expired,
            "expiration_size": duration, # Importante enviar
            "refund_value": 0,
            "price": float(amount),
            "value": 0, 
            "profit_percent": profit_percent
        }

        # Future para resposta imediata do servidor (ACK)
        ack_future = self.dispatcher.create_future(req_id)
        
        # Future para o ID da ordem (Order Created)
        order_id_future = asyncio.get_running_loop().create_future()
        
        def on_order_created(msg):
            # Escuta position-changed com result='opened'
            if msg.get("name") == EV_POSITION_CHANGED:
                raw = msg.get("msg", {})
                evt = raw.get("raw_event", {}).get("binary_options_option_changed1", {})
                
                # Verifica se é a nossa ordem pelo active_id e direction (e tempo recente)
                # O ideal seria bater o external_id, mas no ACK ele vem como 'id' dentro de msg.msg
                # Vamos correlacionar no passo seguinte
                if (str(evt.get("active_id")) == str(active_id) and 
                    evt.get("direction") == direction.lower() and
                    evt.get("result") == "opened"):
                    
                    if not order_id_future.done():
                        # external_id na estrutura raw raiz é o ID da ordem
                        order_id_future.set_result(raw.get("external_id") or raw.get("id"))

        self.dispatcher.add_listener(EV_POSITION_CHANGED, on_order_created)
        
        logger.info("sending_blitz_order", active=active_id, direction=direction)
        
        try:
            # 1. Enviar Request
            await self.ws.send({
                "name": "sendMessage",
                "request_id": req_id,
                "msg": {
                    "name": OP_OPEN_OPTION,
                    "version": "2.0",
                    "body": body
                }
            })
            
            # 2. Esperar ACK (Status 2000)
            ack = await asyncio.wait_for(ack_future, timeout=10.0)
            
            # Validação do ACK
            ack_status = ack.get("status")
            if ack_status not in [0, 2000]:
                msg_err = ack.get("msg")
                if isinstance(msg_err, dict): msg_err = msg_err.get("message")
                raise RuntimeError(f"Erro na abertura da ordem: {msg_err}")

            # O ACK contém o ID da ordem em ack['msg']['id']
            # Podemos usar isso para confirmar o evento position-changed
            created_order_id = ack.get("msg", {}).get("id")
            logger.info("order_ack_received", order_id=created_order_id)

            # 3. Esperar Confirmação de Abertura (Position Changed -> Opened)
            # Se já recebemos o ID no ACK, podemos esperar especificamente por ele
            # Porem, o listener on_order_created já está rodando.
            # Vamos esperar ele capturar ou usar o ID do ACK direto.
            
            # Vamos confiar no ID do ACK para subscrever, pois é mais rápido/seguro
            order_id = created_order_id
            
            self.dispatcher.remove_listener(EV_POSITION_CHANGED, on_order_created) # Limpa listener genérico

            # 4. MONITORAR RESULTADO (WIN/LOOSE)
            # Inscrever especificamente nesse ID é boa prática
            await self.ws.send({
                "name": "sendMessage",
                "request_id": get_req_id(),
                "msg": {
                    "name": OP_SUBSCRIBE_POSITIONS,
                    "version": "1.0",
                    "body": {"frequency": "frequent", "ids": [order_id]}
                }
            })

            result_future = asyncio.get_running_loop().create_future()
            
            def on_result(msg):
                if msg.get("name") == EV_POSITION_CHANGED:
                    raw = msg.get("msg", {})
                    # Verifica ID
                    if str(raw.get("external_id")) == str(order_id) or str(raw.get("id")) == str(order_id):
                        status = raw.get("status")
                        evt = raw.get("raw_event", {}).get("binary_options_option_changed1", {})
                        
                        if status == "closed" or evt.get("result") in ["win", "loose", "equal"]:
                            if not result_future.done():
                                # Parse do resultado
                                pnl = raw.get("pnl", 0) # PNL liquido usado no log
                                profit = raw.get("close_profit", 0) - raw.get("invest", 0)
                                outcome = evt.get("result") or raw.get("close_reason")
                                
                                result_data = {
                                    "status": "closed",
                                    "result": outcome,
                                    "profit": pnl, # Usando PnL do log
                                    "pnl": pnl,
                                    "order_id": order_id
                                }
                                result_future.set_result(result_data)

            self.dispatcher.add_listener(EV_POSITION_CHANGED, on_result)
            
            # Timeout = duração da vela + margem de segurança
            wait_time = max(duration, 60) + 30
            logger.info("waiting_for_result", timeout=wait_time)
            
            trade_result = await asyncio.wait_for(result_future, timeout=wait_time)
            return trade_result

        except asyncio.TimeoutError:
            logger.error("trade_timeout")
            return {"status": "error", "result": "timeout", "pnl": 0}
        except Exception as e:
            logger.error("trade_error", error=str(e))
            raise
        finally:
            if 'on_order_created' in locals():
                self.dispatcher.remove_listener(EV_POSITION_CHANGED, on_order_created)
            if 'on_result' in locals():
                self.dispatcher.remove_listener(EV_POSITION_CHANGED, on_result)
