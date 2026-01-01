import sys
import asyncio
import numpy as np
import pandas as pd
import pandas_ta as ta
import threading
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel
from PyQt5.QtCore import pyqtSignal, QObject, Qt, pyqtSlot
import pyqtgraph as pg

# Imports locais myiq
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
try:
    from myiq import IQOption, Candle, get_all_actives_status
except ImportError:
    pass

# --- CONFIGURAÇÃO ---
EMAIL = "seu_email@exemplo.com"
PASSWORD = "sua_senha"
DEFAULT_ASSET_ID = 76 # EURUSD (padrão)
TIMEFRAME = 60
MIN_PAYOUT = 86

JMA_FAST = 7
JMA_SLOW = 15
JMA_PHASE = 50

# Configuração Martingale
MARTINGALE_STEPS = 5
BASE_AMOUNT = 2.0
FACTOR = 2.3

try:
    from config import EMAIL, PASSWORD
except ImportError:
    pass

# Classe para dados do candle + indicadores "cacheados"
class SmartCandle:
    def __init__(self, raw_candle):
        self.raw = raw_candle
        self.jma_f = np.nan
        self.jma_s = np.nan
        self.is_closed = True # Flag para saber se já calculamos final

    # Getters para facilitar acesso
    @property
    def close(self): return self.raw.close
    @property
    def open(self): return self.raw.open or self.raw.close
    @property
    def id(self): return self.raw.id

class LogicWorker(QObject):
    signal_chart_init = pyqtSignal(list)       # Envia buffer inicial
    signal_candle_update = pyqtSignal(object)  # Atualiza UM candle (o último)
    signal_log = pyqtSignal(str)
    
    # Sinais para marcadores no gráfico
    signal_add_marker = pyqtSignal(float, float, str) # x, y, type (call/put)
    signal_clear_markers = pyqtSignal()               # Limpa tudo no win
    
    # NOVO SINAL: Ticker, Payout, Saldo
    signal_header_info = pyqtSignal(str, str, str)

    def __init__(self):
        super().__init__()
        self.iq = None
        self.running = True
        self.active_id = DEFAULT_ASSET_ID
        self.active_ticker = "---"
        self.payout = 0
        self.current_balance = 0.0
        
        # Buffer fixo de objetos SmartCandle de SmartCandle (já calculados)
        self.buffer = [] 
        self.buffer_lock = threading.Lock()
        
        # Estado do Trade
        self.martingale_level = 0
        self.current_direction = None # 'call' ou 'put'
        self.is_in_operation = False
        
        # Lista negra temporária para ativos com problemas (suspended, fechados)
        self.banned_assets = set()

    async def update_gui_header(self):
        """Atualiza dados do cabeçalho (Saldo, Ativo, Payout)."""
        try:
            bals = await self.iq.get_balances()
            tgt = next((b for b in bals if b.type == 4), None) # Practice
            if not tgt: tgt = next((b for b in bals if b.type == 1), None) # Real
            if tgt: self.current_balance = tgt.amount
        except: pass 
        
        self.signal_header_info.emit(self.active_ticker, f"{self.payout}%", f"${self.current_balance:,.2f}")

    async def run(self):
        self.iq = IQOption(EMAIL, PASSWORD)
        await self.iq.start()
        self.signal_log.emit("Conectado. Aguardando lista de ativos Blitz...")
        
        # --- WAIT FOR CACHE POPULATION ---
        # Espera até detectar ativos no cache, especialmente Blitz
        for _ in range(30):
            # Verifica se já recebeu initialize-data para Blitz ou Turbo
            has_blitz = self.iq.actives_cache.get("blitz")
            has_turbo = self.iq.actives_cache.get("turbo")
            
            if has_blitz or has_turbo:
                # Verifica se o ativo default existe especificamente
                info = self.iq.check_active(self.active_id)
                if info:
                    self.signal_log.emit(f"Cache populado! Status ID {self.active_id}: {info.get('active_type')}")
                    break
            
            await asyncio.sleep(1)
        # ---------------------------------

        self.banned_assets.clear()
        
        await self.select_asset()
        await self.setup_balance()
        await self.update_gui_header() # Init

        while self.running:
            if not await self.ensure_connection():
                await asyncio.sleep(2)
                continue

            if not self.buffer:
                await self.initialize_buffer()
            
            # Atualiza saldo periodicamente (a cada ~10s)
            if int(datetime.now().timestamp()) % 10 == 0:
                await self.update_gui_header()

            await asyncio.sleep(1)

        await self.iq.close()

    async def select_asset(self):
        """Busca melhor ativo Aberto (APENAS BLITZ) com Payout > MIN."""
        self.signal_log.emit(f"Selecionando melhor ativo BLITZ (Ignorando: {self.banned_assets})...")
        
        current_valid = False
        if self.active_id not in self.banned_assets:
            try:
                # Checa status usando o método inteligente da lib (Prioridade Blitz > Turbo)
                info = self.iq.check_active(self.active_id)
                
                if info:
                    self.active_ticker = info.get('name') or info.get('ticker', str(self.active_id))
                    
                    # Logica unificada de 'Aberto' da lib (enabled=True, suspended=False)
                    is_open = self.iq.is_active_open(self.active_id)
                    
                    # Profit percent também centralizado
                    prof = self.iq.get_profit_percent(self.active_id)
                    
                    if is_open:
                        self.payout = prof
                        if prof >= MIN_PAYOUT:
                            self.signal_log.emit(f"Ativo Atual {self.active_ticker} OK (Payout {prof}% exatos). Mantendo.")
                            current_valid = True
                        else:
                            self.signal_log.emit(f"Ativo Atual Payout Baixo ({prof}%). Buscando novo...")
                    else:
                        self.signal_log.emit(f"Ativo {self.active_ticker} Fechado (is_open=False).")
                        self.banned_assets.add(self.active_id)
            except: pass
        
        if current_valid: 
            await self.update_gui_header()
            return

        self.signal_log.emit("Buscando lista de ativos BLITZ...")
        try:
            # Busca apenas BLITZ pois a lib só tem buy_blitz
            all_actives = await get_all_actives_status(self.iq, "blitz")
            
            best_id = None
            best_pay = 0
            best_ticker = ""
            
            for aid, inf in all_actives.items():
                if int(aid) in self.banned_assets: continue
                if inf.get('is_open') and not inf.get('suspended'):
                    p = inf.get('profit_percent', 0)
                    if p >= MIN_PAYOUT and p > best_pay:
                        best_pay = p
                        best_id = int(aid)
                        best_ticker = inf.get('ticker')
            
            if best_id:
                old_id = self.active_id
                self.active_id = best_id
                self.active_ticker = best_ticker
                self.payout = best_pay
                self.signal_log.emit(f">>> NOVO ATIVO: {best_ticker} ({best_id}) | Payout: {best_pay}%")
                
                if old_id != best_id:
                    with self.buffer_lock:
                        self.buffer = []
            else:
                self.signal_log.emit("Nenhum ativo BLITZ adequado encontrado. Aguardando...")
                self.active_id = None 
                self.active_ticker = "---"
                
        except Exception as e:
            self.signal_log.emit(f"Erro ao buscar ativos: {e}")
            
        await self.update_gui_header()

    async def setup_balance(self):
        try:
            bals = await self.iq.get_balances()
            # Prioriza Practice (type 4) depois Real (type 1)
            tgt = next((b for b in bals if b.type == 4), None)
            if not tgt: tgt = next((b for b in bals if b.type == 1), None)
            
            if tgt:
                await self.iq.change_balance(tgt.id)
                self.signal_log.emit(f"Saldo conta: {tgt.amount}")
        except:
            pass

    async def ensure_connection(self):
        # Lógica simples de check
        connected = False
        if hasattr(self.iq, 'check_connect'): connected = self.iq.check_connect()
        else: connected = (self.iq.ws and self.iq.ws.is_connected and self.iq.ssid)
        
        if not connected:
            self.signal_log.emit("Reconectando...")
            return False
            
        # Se não temos ativo selecionado (falha na busca), tenta buscar de novo
        if not self.active_id:
            await self.select_asset()
            
        return True

    async def initialize_buffer(self):
        """Baixa histórico de 100 velas."""
        if not self.active_id: return
        
        self.signal_log.emit(f"Iniciando ativo {self.active_id}... Baixando Histórico.")
        try:
            raw = await self.iq.fetch_candles(self.active_id, TIMEFRAME, 300)
        except Exception as e:
            self.signal_log.emit(f"Erro fetch candles: {e}. Tentando outro ativo.")
            self.banned_assets.add(self.active_id)
            await self.select_asset()
            return
        
        with self.buffer_lock:
            self.buffer = [SmartCandle(c) for c in raw]
            # Calc inicial
            jf, js = self.calculate_single_candle(self.buffer) # Calc dummy pra popular cache interno
            # O calculate_single_candle retorna so o ultimo. 
            # Precisamos popular TODOS do historico para o grafico inicial ficar bonito.
            
            # --- POPULAR HISTORICO (Init) ---
            df = pd.DataFrame({'close': [c.close for c in self.buffer]})
            jma_f = ta.jma(df['close'], length=JMA_FAST, phase=JMA_PHASE)
            jma_s = ta.jma(df['close'], length=JMA_SLOW, phase=JMA_PHASE)
            
            for i, c in enumerate(self.buffer):
                c.jma_f = jma_f.iloc[i] if not pd.isna(jma_f.iloc[i]) else np.nan
                c.jma_s = jma_s.iloc[i] if not pd.isna(jma_s.iloc[i]) else np.nan

        # Envia para GUI
        self.signal_chart_init.emit(self.buffer[-80:])
        self.signal_log.emit("Stream iniciado.")
        
        await self.iq.start_candles_stream(self.active_id, TIMEFRAME, self.on_stream_data)


    # ... (calculate_single_candle fica igual) ...
    def calculate_single_candle(self, full_list_of_smart_candles):
        subset = full_list_of_smart_candles # Usa tudo
        closes = [c.close for c in subset]
        s_close = pd.Series(closes)
        try:
            j_f = ta.jma(s_close, length=JMA_FAST, phase=JMA_PHASE)
            j_s = ta.jma(s_close, length=JMA_SLOW, phase=JMA_PHASE)
            last_f = j_f.iloc[-1] if j_f is not None and not pd.isna(j_f.iloc[-1]) else np.nan
            last_s = j_s.iloc[-1] if j_s is not None and not pd.isna(j_s.iloc[-1]) else np.nan
            return last_f, last_s
        except:
            return np.nan, np.nan

    # ... (on_stream_data mantem logica, exceto o buffer size) ...
    def on_stream_data(self, data):
        c_new = Candle(**data)
        with self.buffer_lock:
            if not self.buffer: return
            last_smart = self.buffer[-1]
            if c_new.id != last_smart.id:
                # FECHOU
                jf, js = self.calculate_single_candle(self.buffer)
                last_smart.jma_f = jf; last_smart.jma_s = js
                last_smart.is_closed = True
                self.check_entry_logic()
                # NOVO
                new_smart = SmartCandle(c_new)
                new_smart.is_closed = False
                self.buffer.append(new_smart)
                if len(self.buffer) > 300: self.buffer.pop(0)
                # Calc forming
                jf, js = self.calculate_single_candle(self.buffer)
                new_smart.jma_f = jf; new_smart.jma_s = js
            else:
                # UPDATE
                last_smart.raw.close = c_new.close
                last_smart.raw.max = c_new.max
                last_smart.raw.min = c_new.min
                jf, js = self.calculate_single_candle(self.buffer)
                last_smart.jma_f = jf; last_smart.jma_s = js
                
        self.signal_candle_update.emit(self.buffer[-1])

    # ... (check_entry_logic mantem igual) ...
    def check_entry_logic(self):
        if self.is_in_operation: return
        if len(self.buffer) < 3: return
        last = self.buffer[-1]; prev = self.buffer[-2]
        if np.isnan(last.jma_f) or np.isnan(prev.jma_s): return
        lf, ls = last.jma_f, last.jma_s
        pf, ps = prev.jma_f, prev.jma_s
        cross_up = (pf <= ps) and (lf > ls)
        cross_down = (pf >= ps) and (lf < ls)
        diff = abs(lf - ls)
        threshold = last.close * 0.00003 
        valid_cross = False; direction = None
        
        if cross_up and diff > threshold: direction = 'call'; valid_cross = True
        elif cross_down and diff > threshold: direction = 'put'; valid_cross = True
            
        if self.martingale_level > 0:
            final_dir = self.current_direction
            if valid_cross:
                self.signal_log.emit(f"Martingale: Reverso detectado para {direction.upper()}!")
                final_dir = direction
                self.current_direction = direction
            self.execute_trade(final_dir, is_martingale=True)
        else:
            if valid_cross:
                self.signal_log.emit(f"Sinal Principal {direction.upper()} detectado.")
                self.current_direction = direction
                self.execute_trade(direction, is_martingale=False)

    def execute_trade(self, direction, is_martingale=False):
        # Valor
        amount = BASE_AMOUNT
        if is_martingale:
            amount = BASE_AMOUNT * (FACTOR ** self.martingale_level)
            
        self.is_in_operation = True # Bloqueia novas análises
        # Passamos o ID do ativo ATUAL para garantir que a task não opere ativo errado após troca
        asyncio.create_task(self._trade_task(direction, amount, self.active_id))

    async def _trade_task(self, direction, amount, trade_active_id):
        chaining_martingale = False # Flag para controlar lock em caso de gale imediato
        try:
            # 1. Verificação de Integridade (Race Condition)
            if trade_active_id != self.active_id:
                self.signal_log.emit(f"Trade abortado: Ativo mudou de {trade_active_id} para {self.active_id}.")
                return

            lbl = f"GALE {self.martingale_level}" if self.martingale_level > 0 else "MAIN"
            self.signal_log.emit(f">>> ABRINDO {lbl}: {direction.upper()} ${amount:.2f} (Payout {self.payout}%)")
            
            # 2. Acesso Seguro ao Buffer (Lock)
            entry_price = 0.0
            with self.buffer_lock:
                if not self.buffer:
                    self.signal_log.emit("Erro Crítico: Buffer vazio na execução do trade.")
                    return
                entry_price = self.buffer[-1].close
                
            self.signal_add_marker.emit(float(entry_price), float(entry_price), direction)
            
            # --- TENTATIVA DE TRADE ---
            # Usa o trade_active_id capturado na origem
            # DURATION: enviamos TIMEFRAME (60s) pois a lib espera segundos em 'expiration_size'
            result = await self.iq.buy_blitz(trade_active_id, direction, amount, TIMEFRAME) 
            
            status = result.get('result')
            error_msg = str(result.get('error', '')) or str(result.get('message', ''))
            
            # --- DETECÇÃO DE ATIVO RUIM ---
            if "suspended" in error_msg.lower() or "closed" in error_msg.lower():
                self.signal_log.emit(f"ERRO CRÍTICO: Ativo {trade_active_id} Suspenso! Banindo e trocando...")
                self.banned_assets.add(trade_active_id)
                self.is_in_operation = False
                # Inicia troca de ativo em background
                asyncio.create_task(self.select_asset())
                return # Sai da task
            
            profit = result.get('pnl', 0)
            self.signal_log.emit(f"Resultado: {str(status).upper()} | Lucro: {profit}")
            
            # Atualiza Saldo após trade
            await self.update_gui_header()
            
            if status == 'win':
                self.signal_log.emit(">>> WIN! Reiniciando ciclo.")
                self.martingale_level = 0
                self.current_direction = None
                self.signal_clear_markers.emit() 
            else:
                self.signal_log.emit(">>> LOSS. Preparando Martingale.")
                if self.martingale_level < MARTINGALE_STEPS:
                    self.martingale_level += 1
                    self.signal_log.emit(f"Executando Martingale Nível {self.martingale_level} IMEDIATAMENTE.")
                    
                    # --- GALE IMEDIATO ---
                    chaining_martingale = True # Impede o unlock no finally
                    # Chama execute_trade (que é síncrono e spawna a task)
                    self.execute_trade(direction, is_martingale=True)
                else:
                    self.signal_log.emit(">>> STOP LOSS (Max Gales). Resetando.")
                    self.martingale_level = 0
                    self.current_direction = None
                    self.signal_clear_markers.emit()

        except Exception as e:
            err_msg = str(e).lower()
            if "suspended" in err_msg or "closed" in err_msg or "inactive" in err_msg:
                 self.signal_log.emit(f"ERRO CRÍTICO: Ativo {trade_active_id} Suspenso/Fechado! Banindo e Trocando...")
                 self.banned_assets.add(trade_active_id)
                 self.is_in_operation = False
                 # Inicia troca de ativo em background
                 asyncio.create_task(self.select_asset())
            else:
                 self.signal_log.emit(f"Erro Trade Genérico: {e}")
                 
        finally:
            # SO LIBERA O SISTEMA SE NAO ESTIVER ENCADEANDO GALE
            if not chaining_martingale:
                self.is_in_operation = False

# --- GUI: CHART WINDOW ---

# --- GUI: PROFESSIONAL CHART WINDOW ---

from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QPushButton, QProgressBar, 
                             QGraphicsDropShadowEffect, QTextEdit, QSplitter)
from PyQt5.QtGui import QColor, QFont, QPalette, QBrush

class ModernChart(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JMA PRO TRADER AI - v2.0")
        self.resize(1280, 720)
        
        # --- THEME & STYLE ---
        self.setStyleSheet("""
            QMainWindow { background-color: #121212; }
            QWidget { font-family: 'Segoe UI', sans-serif; font-size: 13px; color: #e0e0e0; }
            
            QFrame#TopBar { 
                background-color: #1e1e1e; 
                border-bottom: 1px solid #333; 
                border-radius: 5px;
            }
            
            QLabel#Title { font-size: 16px; font-weight: bold; color: #00ffca; }
            QLabel#Status { color: #888; }
            QLabel#InfoBox { font-weight: bold; color: #fff; padding: 0 10px; }
            
            QTextEdit { 
                background-color: #0f0f0f; 
                border: 1px solid #333; 
                border-radius: 4px; 
                color: #0f0; 
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
        """)

        # Main Layout
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 1. TOP HEADER (Info Bar)
        self.header = QFrame()
        self.header.setObjectName("TopBar")
        self.header.setFixedHeight(50)
        header_layout = QHBoxLayout(self.header)
        
        # Title
        title = QLabel("JMA BOT INTELLIGENCE")
        title.setObjectName("Title")
        
        # Status Infos
        self.lbl_asset = QLabel("ASSET: ---")
        self.lbl_asset.setObjectName("InfoBox")
        
        self.lbl_payout = QLabel("PAYOUT: ---%")
        self.lbl_payout.setObjectName("InfoBox")
        
        self.lbl_balance = QLabel("BALANCE: ---")
        self.lbl_balance.setObjectName("Balance")
        self.lbl_balance.setStyleSheet("color: #00ff00; font-weight: bold; padding: 0 10px; font-size: 14px;")
        
        self.lbl_last_price = QLabel("PRICE: ---")
        self.lbl_last_price.setObjectName("InfoBox")
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_asset)
        header_layout.addWidget(self.lbl_payout)
        header_layout.addWidget(self.lbl_balance)
        header_layout.addWidget(self.lbl_last_price)
        
        # Add Header shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.header.setGraphicsEffect(shadow)
        
        main_layout.addWidget(self.header)

        # 2. CHART AREA
        self.plot_item = pg.PlotWidget()
        self.plot_item.setBackground('#1e1e1e')
        self.plot_item.showGrid(x=True, y=True, alpha=0.15)
        self.plot_item.getAxis('bottom').setPen(color='#555')
        self.plot_item.getAxis('left').setPen(color='#555')
        
        # Styling Chart
        self.curve_price = self.plot_item.plot(pen=pg.mkPen('#ffffff', width=2), name="Price") # Clean White
        # JMA Fast = Cyan Neon, JMA Slow = Magenta Neon (Cyberpunk style)
        self.curve_jma_f = self.plot_item.plot(pen=pg.mkPen('#00e5ff', width=2, style=Qt.SolidLine), name="JMA Fast")
        self.curve_jma_s = self.plot_item.plot(pen=pg.mkPen('#ff0033', width=2, style=Qt.SolidLine), name="JMA Slow")
        
        # Gradient Fill for JMA crossover? (Optional, lets keep clean)

        # Markers
        self.markers = pg.ScatterPlotItem(size=14, pen=pg.mkPen('#000', width=1))
        self.plot_item.addItem(self.markers)
        self.marker_spots = []

        # Legend
        legend = self.plot_item.addLegend(offset=(30, 30))
        legend.setBrush(pg.mkBrush(0, 0, 0, 100))
        legend.setLabelTextColor("#ccc")

        main_layout.addWidget(self.plot_item, stretch=3)

        # 3. LOG CONSOLE
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(150)
        self.console.setPlaceholderText("System Ready. Waiting for signals...")
        
        main_layout.addWidget(self.console, stretch=1)

        # Data State
        self.data_price = []
        self.data_jf = []
        self.data_js = []
        self.x_axis = []
        self.count = 0 
        self.last_seen_id = None

    @pyqtSlot(str, str, str)
    def update_header_info(self, active_ticker, payout, balance):
        """Slot para atualizar cabeçalho direto do worker."""
        self.lbl_asset.setText(f"ASSET: {active_ticker}")
        self.lbl_payout.setText(f"PAYOUT: {payout}")
        self.lbl_balance.setText(f"BALANCE: {balance}")

    @pyqtSlot(list)
    def init_chart(self, initial_candles):
        """Recebe lista inicial (~50 candles). Sobrescreve tudo."""
        if not initial_candles: return
        
        self.data_price = [c.close for c in initial_candles]
        self.data_jf = [c.jma_f for c in initial_candles]
        self.data_js = [c.jma_s for c in initial_candles]
        self.count = len(initial_candles)
        self.x_axis = list(range(self.count))
        
        self._refresh_plot()
        self.log_html(f"<span style='color:cyan'>System Initialized. Loaded {len(initial_candles)} candles.</span>")

    @pyqtSlot(object)
    def update_candle(self, smart_candle):
        if not self.data_price: return

        cid = smart_candle.id
        price = smart_candle.close
        jf = smart_candle.jma_f
        js = smart_candle.jma_s
        
        # --- UPDATE PRICE LABEL ---
        self.lbl_last_price.setText(f"PRICE: {price:.5f}")
        
        # --- ATUALIZAÇÃO DO GRÁFICO (Live) ---
        if self.last_seen_id == cid:
            # Update último ponto (vela em formação)
            if self.data_price: self.data_price[-1] = price
            if self.data_jf: self.data_jf[-1] = jf
            if self.data_js: self.data_js[-1] = js
        else:
            # Novo ponto (vela fechou)
            self.data_price.append(price)
            self.data_jf.append(jf)
            self.data_js.append(js)
            self.count += 1
            self.x_axis.append(self.count)
            self.last_seen_id = cid
            
        # Mantém janela deslizante
        MAX_VIEW = 100
        if len(self.data_price) > MAX_VIEW:
            self.data_price = self.data_price[-MAX_VIEW:]
            self.data_jf = self.data_jf[-MAX_VIEW:]
            self.data_js = self.data_js[-MAX_VIEW:]
            self.x_axis = self.x_axis[-MAX_VIEW:]
        
        self._refresh_plot()

    @pyqtSlot(str)
    def log(self, txt):
        print(txt) # Keep console print
        
        # Colorize logs
        color = "#ccc"
        if "WIN" in txt: color = "#00ff00"
        elif "LOSS" in txt or "Erro" in txt or "CRÍTICO" in txt: color = "#ff0000"
        elif "COMPRA" in txt or "CALL" in txt: color = "#00ffff"
        elif "VENDA" in txt or "PUT" in txt: color = "#ff00ff"
        elif "Martingale" in txt: color = "#ffa500"
        
        self.log_html(f"<span style='color:{color}'>{txt}</span>")

    def log_html(self, html):
        self.console.append(html)
        # Auto scroll
        sb = self.console.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _refresh_plot(self):
        self.curve_price.setData(self.x_axis, self.data_price)
        self.curve_jma_f.setData(self.x_axis, self.data_jf, connect="finite")
        self.curve_jma_s.setData(self.x_axis, self.data_js, connect="finite")

    @pyqtSlot(float, float, str)
    def add_marker(self, y_val, _, direction):
        # Cor
        if direction == 'call':
            brush = pg.mkBrush('#00ff00')
            symbol = 't1' # Triangulo Up
        else:
            brush = pg.mkBrush('#ff0000')
            symbol = 't' # Triangulo Down
        
        # A posição X sempre atrelada ao último candle (self.count)
        spot = {'pos': (self.count, y_val), 'size': 14, 'pen': pg.mkPen('w'), 'brush': brush, 'symbol': symbol}
        self.marker_spots.append(spot)
        self.markers.setData(self.marker_spots)
    
    @pyqtSlot()
    def clear_markers(self):
        self.marker_spots = []
        self.markers.setData([])

def main():
    app = QApplication(sys.argv)
    
    # Set Fusion Style for better default widgets
    app.setStyle("Fusion")
    
    # Global Palette Dark
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(18, 18, 18))
    palette.setColor(QPalette.WindowText, Qt.white)
    app.setPalette(palette)
    
    win = ModernChart()
    win.show()
    
    worker = LogicWorker()
    worker.signal_chart_init.connect(win.init_chart)
    worker.signal_candle_update.connect(win.update_candle)
    worker.signal_log.connect(win.log)
    worker.signal_add_marker.connect(win.add_marker)
    worker.signal_clear_markers.connect(win.clear_markers)
    worker.signal_header_info.connect(win.update_header_info)
    
    # Thread separada para lógica async
    t = threading.Thread(target=lambda: asyncio.run(worker.run()), daemon=True)
    t.start()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

