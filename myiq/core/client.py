
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
        from collections import defaultdict
        self.actives_cache = defaultdict(dict) # { type_name: { active_id: data } }
        # New attributes for storing message data
        self.profile = {}
        self.features = {}
        self.user_settings = {}
        self.instruments_categories = {} # from initialization-data

    async def subscribe_actives(self):
        """
        Inscreve para receber atualizações da lista de ativos (underlying-list-changed).
        Isso popula self.actives_cache.
        """
        # Digital
        await self.ws.send({
            "name": "subscribeMessage",
            "request_id": get_req_id(),
            "msg": {
                "name": "digital-option-instruments.underlying-list-changed",
                "version": "3.0",
                "params": {"routingFilters": {"user_group_id": 1, "is_regulated": False}}
            }
        })
        # Turbo (Blitz/Short)
        await self.ws.send({
            "name": "subscribeMessage",
            "request_id": get_req_id(),
            "msg": {
                "name": "turbo-option-instruments.underlying-list-changed",
                "version": "3.0",
                "params": {"routingFilters": {"user_group_id": 1, "is_regulated": False}}
            }
        })
        # Binary (Long)
        await self.ws.send({
            "name": "subscribeMessage",
            "request_id": get_req_id(),
            "msg": {
                "name": "binary-option-instruments.underlying-list-changed",
                "version": "3.0",
                "params": {"routingFilters": {"user_group_id": 1, "is_regulated": False}}
            }
        })
        # Blitz (New Support)
        await self.ws.send({
            "name": "subscribeMessage",
            "request_id": get_req_id(),
            "msg": {
                "name": "blitz-option-instruments.underlying-list-changed",
                "version": "3.0", # Assuming schema follows others
                "params": {"routingFilters": {"user_group_id": 1, "is_regulated": False}}
            }
        })
        logger.info("actives_list_subscribed")

    def _on_underlying_list_changed(self, message: dict):
        try:
            # Determine type from message name if possible
            msg_name = message.get("msg", {}).get("name", "")
            active_type = "unknown"
            
            if "digital-option" in msg_name:
                active_type = "digital-option"
            elif "turbo-option" in msg_name:
                active_type = "turbo-option" # Covers Blitz
            elif "binary-option" in msg_name:
                active_type = "binary-option"
            elif "blitz-option" in msg_name:
                active_type = "blitz-option" # Explicit blitz support
            
            # If msg_name is generic 'underlying-list-changed', try to infer or default
            # But usually it has the prefix. If not, we might be overwriting unknown types.
                
            msg = message.get("msg", {})
            underlying_list = msg.get("underlying", [])
            
            count = 0
            for item in underlying_list:
                active_id = str(item.get("active_id"))
                if active_id:
                    # Save into nested dict: cache[type][id]
                    self.actives_cache[active_type][active_id] = item
                    item["active_type"] = active_type # Inject type into data too
                    count += 1
            
            logger.info("actives_cache_updated", type=active_type, count=count)
        except Exception as e:
            logger.error("update_actives_error", error=str(e))

    def _on_profile(self, message: dict):
        """Handler for 'profile' message."""
        try:
            msg = message.get("msg", {})
            if msg:
                self.profile = msg
                logger.info("profile_updated", user_id=self.profile.get("user_id"))
        except Exception as e:
            logger.error("profile_parse_error", error=str(e))

    def _on_features(self, message: dict):
        """Handler for 'features' message."""
        try:
            msg = message.get("msg", {})
            features_list = msg.get("features", [])
            # Store simply as a dict {id: status} or similar, or just raw
            for feat in features_list:
                name = feat.get("name")
                status = feat.get("status")
                if name:
                    self.features[name] = status
            logger.info("features_updated", count=len(self.features))
        except Exception as e:
            logger.error("features_parse_error", error=str(e))

    def _on_user_settings(self, message: dict):
        """Handler for 'user-settings'."""
        try:
            # The message structure from log: {"name":"user-settings","msg":{"configs":[...]}}
            # But sometimes it might be just the msg depending on dispatcher.
            # Our dispatcher sends the WHOLE message to callbacks.
            msg = message.get("msg", {})
            configs = msg.get("configs", [])
            for conf in configs:
                name = conf.get("name")
                if name:
                    self.user_settings[name] = conf.get("config")
            logger.info("user_settings_updated")
        except Exception as e:
            logger.error("settings_parse_error", error=str(e))


    def _on_initialization_data(self, message: dict):
        """Handler for 'initialization-data'."""
        try:
            # message['msg'] keys are categories: 'turbo', 'binary', 'blitz', 'digital', 'forex', etc.
            msg = message.get("msg", {})
            
            count_new = 0
            
            # Dynamic parsing: Iterate over all keys regardless of name
            for category_name, category_data in msg.items():
                if isinstance(category_data, dict):
                    actives_dict = category_data.get("actives")
                    
                    if isinstance(actives_dict, dict):
                        # category_name is exactly 'blitz', 'turbo', etc.
                        # Save directly to cache[category_name]
                        for a_id, a_data in actives_dict.items():
                            s_id = str(a_id)
                            # Enforce active_type if missing
                            if "active_type" not in a_data:
                                a_data["active_type"] = category_name
                                
                            self.actives_cache[category_name][s_id] = a_data
                            count_new += 1
            
            logger.info("init_data_processed", merged_active_items=count_new)
        except Exception as e:
            logger.error("init_data_error", error=str(e))
        except Exception as e:
            logger.error("init_data_error", error=str(e))

    async def start(self):
        self.ssid = await self.auth.get_ssid()
        
        # Reconexão Automática: Registrar Callback
        self.ws.on_reconnect = self._on_reconnect
        self.ws.on_message_hook = self._on_ws_message
        
        logger.info("connecting_ws")
        
        
        # Registra listener para lista de ativos
        self.dispatcher.add_listener(EV_UNDERLYING_LIST_CHANGED, self._on_underlying_list_changed)
        
        # Registra listeners para os novos tipos de mensagem
        self.dispatcher.add_listener(EV_PROFILE, self._on_profile)
        self.dispatcher.add_listener(EV_FEATURES, self._on_features)
        self.dispatcher.add_listener(EV_USER_SETTINGS, self._on_user_settings)
        # some logs show "set-user-settings" as trigger? No, usually "user-settings" is the event name.
        self.dispatcher.add_listener(EV_INIT_DATA, self._on_initialization_data)
        
        await self.ws.connect()
        
        logger.info("authenticating_ws")
        await self._authenticate()
        
        # Request initialization data explicitly (crucial for getting active lists like blitz)
        await self.ws.send({
            "name": "sendMessage",
            "request_id": get_req_id(),
            "msg": {
                "name": "get-initialization-data",
                "version": "4.0",
                "body": {}
            }
        })
            
        await self.subscribe_portfolio()
        await self.subscribe_actives()
        
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
            await self.subscribe_actives()
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

    async def get_financial_info(self, active_id: int):
        """
        Request detailed financial information (GraphQL) for an active.
        This provides technical indicators changes (m1, ytd), full name, description, etc.
        """
        req_id = get_req_id()
        future = self.dispatcher.create_future(req_id)
        
        # The complex GraphQL query from the logs
        query = """query GetAssetProfileInfo($activeId:ActiveID!, $locale: LocaleName, $instrumentType: InstrumentTypeName!, $userGroupId: UserGroupID){
      active(id: $activeId) {
        id
        name(source: TradeRoom, locale: $locale)
        ticker
        price
        media {
          siteBackground
        }
        
        expirations(instrument: $instrumentType, userGroupID: $userGroupId) {
            endOfDay
            endOfHour
            endOfMonth
            endOfWeek
            min(instrument: $instrumentType)
            values(instrument: $instrumentType) {
                value
            }
        }
        charts {
          dtd {
            change
          }
          m1 {
            change
          }
          y1 {
            change
          }
          ytd {
            change
          }
        }
        index_fininfo: fininfo {
          ... on Index {
            description(locale: $locale)
          }
        }
        fininfo {
          ... on Pair {
            type
            description(locale: $locale)
            currency {
              name(locale: $locale)
            }
            base {
              name(locale: $locale)
              ... on Stock {
                company {
                  country {
                    nameShort
                  }
                  gics {
                    sector(locale: $locale)
                    industry(locale: $locale)
                  }
                  site
                  domain
                }
                keyStat {
                  marketCap
                  peRatioHigh
                }
              }
              ... on CryptoCurrency {
                site
                domain
                coinsInCirculation
                maxCoinsQuantity
                volume24h
                marketCap
              }
            }
          }
        }
      }
    }"""
        
        # We need to guess or default some params.
        # instrumentType: "BlitzOption" works for blitz, but maybe dynamic? 
        # For general safety we can use "DigitalOption" or stick to what log showed if it's generic.
        # The log used "BlitzOption" for active 2276. Let's try to infer or default.
        inst_type = "BlitzOption"
        
        payload = {
            "name": "sendMessage", # Wrapped message
            "request_id": req_id,
            "msg": {
                "name": OP_GET_FINANCIAL_INFO,
                "version": "1.0",
                "body": {
                    "query": query,
                    "variables": {
                        "activeId": int(active_id),
                        "locale": "pt_PT", # Hardcoded to user preference or config
                        "instrumentType": inst_type,
                        "userGroupId": 1 # Default group
                    },
                    "operationName": "GetAssetProfileInfo"
                }
            }
        }
        
        await self.ws.send(payload)
        
        try:
            res = await asyncio.wait_for(future, timeout=10.0)
            # The structure is res['msg']['data']['active']
            return res.get("msg", {}).get("data", {}).get("active", {})
        except asyncio.TimeoutError:
            logger.error("financial_info_timeout", active_id=active_id)
            return None
        except Exception as e:
            logger.error("financial_info_error", error=str(e))
            return None

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
        # "Shotgun" approach: Configura o Grid para todos os tipos possíveis.
        # Isso garante que o stream inicie independente se é Turbo, Binary, Digital ou Blitz sem o usuário precisar adivinhar.
        types_to_try = [INSTRUMENT_TYPE_BLITZ, "turbo-option", "binary-option", "digital-option"]
        
        plotters = []
        for t in types_to_try:
            plotters.append({
                "activeId": active_id,
                "activeType": t,
                "plotType": "candles",
                "candleDuration": duration,
                "isMinimized": False
            })

        grid_payload = {
            "name": "traderoom_gl_grid",
            "version": 2,
            "client_id": get_client_id(),
            "config": {
                "name": "default",
                "fixedNumberOfPlotters": len(plotters),
                "plotters": plotters,
                "selectedActiveId": active_id
            }
        }
        
        await self.ws.send({
            "name": "sendMessage",
            "request_id": get_req_id(),
            "msg": {"name": OP_SET_SETTINGS, "version": "1.0", "body": grid_payload}
        })
        
        # 2. Inscreve no canal também por segurança
        # Formato estrito conforme solicitado pelo usuário (sem versão)
        await self.ws.send({
            "name": "subscribeMessage",
            "request_id": get_sub_id(),
            "msg": {
                "name": EV_CANDLE_GENERATED,
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

    def get_active(self, active_id: int) -> dict:
        """
        Retrieves active info looking into all cache categories with priority.
        Priority: blitz > turbo > binary > digital
        """
        s_id = str(active_id)
        # Prioridade baseada na modernidade (Blitz é mais recente/rápido)
        priorities = ["blitz", "turbo", "binary", "digital", "digital-option"]
        
        # 1. Busca Direcionada
        for cat in priorities:
            data = self.actives_cache.get(cat, {}).get(s_id)
            if data:
                return data
        
        # 2. Varredura Genérica (caso haja categorias novas não mapeadas)
        for cat, cache in self.actives_cache.items():
            if isinstance(cache, dict):
                data = cache.get(s_id)
                if data:
                    return data
                    
        return {}

    def check_active(self, active_id: int) -> dict:
        """
        Returns the cached status of an active using smart lookup. 
        Returns an empty dict if not found.
        """
        return self.get_active(active_id)

    def get_profit_percent(self, active_id: int) -> int:
        """
        Returns the profit percentage for the active (e.g. 86).
        Calculates from commission if explicit field is missing.
        """
        data = self.check_active(active_id)
        
        # 1. Try direct field
        if "profit_percent" in data:
            return data["profit_percent"]
            
        # 2. Try calculation from commission (100 - commission)
        # Structure: data['option']['profit']['commission']
        try:
            commission = data.get("option", {}).get("profit", {}).get("commission")
            if commission is not None:
                return 100 - int(commission)
        except:
            pass
            
        return 0

    def is_active_open(self, active_id: int) -> bool:
        """Checks if the active is currently open for trading."""
        info = self.check_active(active_id)
        return info.get("enabled", False) and not info.get("is_suspended", True)

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
                    # A estrutura pode vir de diferentes formas, precisamos checar todas
                    # IDs podem ser string ou int
                    msg_id = raw.get("id")
                    external_id = raw.get("external_id")
                    
                    is_same_id = (str(msg_id) == str(order_id) or str(external_id) == str(order_id))
                    
                    if is_same_id:
                        status = raw.get("status")
                        evt = raw.get("raw_event", {}).get("binary_options_option_changed1", {})
                        
                        # O evento de fechamento geralmente tem status 'closed' OU o evento interno tem 'result'
                        # Logs mostram result='win' no evento interno e status='closed' no externo
                        
                        is_closed = (status == "closed")
                        has_result = (evt.get("result") in ["win", "loose", "equal"])
                        
                        if is_closed or has_result:
                            if not result_future.done():
                                # Parse do resultado
                                # O PNL correto vem geralmente no nível raiz do msg ou calculado
                                # Log: "pnl":0.8600000000000001
                                pnl = raw.get("pnl", 0)
                                if pnl == 0 and "profit_amount" in evt:
                                     # Fallback calcular PNL
                                     net = evt.get("profit_amount", 0) - evt.get("amount", 0)
                                     pnl = net
                                
                                outcome = evt.get("result") or raw.get("close_reason")
                                
                                result_data = {
                                    "status": "closed",
                                    "result": outcome,
                                    "profit": pnl, 
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
