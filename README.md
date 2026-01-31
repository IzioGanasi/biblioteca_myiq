# 🚀 myiq: High-Performance IQ Option Async Framework

`myiq` é uma biblioteca Python assíncrona de nível industrial para automação e análise de dados na IQ Option. Diferente de outras bibliotecas, ela foca em **estabilidade de conexão**, **tipagem estática** e suporte nativo às APIs modernas da plataforma, incluindo **Blitz Options** e **GraphQL**.

## 📌 Sumário
- [Arquitetura Core](#-arquitetura-core)
- [Instalação e Setup](#-instalação-e-setup)
- [Autenticação e Conexão](#-autenticação-e-conexão)
- [Gerenciamento de Saldo](#-gerenciamento-de-saldo)
- [Exploração de Mercado e Ativos](#-exploração-de-mercado-e-ativos)
- [Dados Históricos (Candles)](#-dados-históricos-candles)
- [Streaming em Tempo Real (Shotgun Pattern)](#-streaming-em-tempo-real-shotgun-pattern)
- [Execução de Trading (Blitz Options)](#-execução-de-trading-blitz-options)
- [Informações Financeiras Avançadas (GraphQL)](#-informações-financeiras-avançadas-graphql)
- [Sistema de Eventos (Dispatcher)](#-sistema-de-eventos-dispatcher)


## 🏗 Arquitetura Core

A biblioteca é dividida em camadas modulares:
1.  **ReconnectingWS**: Wrapper inteligente que monitora o WebSocket e realiza backoff exponencial em caso de queda.
2.  **Dispatcher**: Central de eventos que roteia mensagens do servidor para `Futures` (respostas diretas) ou `Listeners` (eventos contínuos).
3.  **Models**: Baseado em `Pydantic` para garantir que os dados recebidos da corretora estejam no formato esperado.

---

## 🛠 Instalação e Setup

```bash
pip install git+https://github.com/IzioGanasi/biblioteca_myiq.git
```

```bash
pip install httpx websockets structlog pydantic
```

---

## 🔐 Autenticação e Conexão

O processo de login é duplo: primeiro via API REST para obter o `SSID` e depois via WebSocket para autenticação de trading.

```python
from myiq.core.iqoption import IQOption
import asyncio

async def run():
    iq = IQOption("email@exemplo.com", "senha123")
    
    # Inicia conexão, autentica e sincroniza relógio do servidor
    await iq.start()
    
    if iq.check_connect():
        print(f"Server Time Offset: {iq.server_time_offset}ms")
```

---

## 💰 Gerenciamento de Saldo

Suporta múltiplas contas (Real, Prática, Torneio).

```python
balances = await iq.get_balances()
for b in balances:
    print(f"ID: {b.id} | Tipo: {b.type} | Moeda: {b.currency} | Valor: {b.amount}")

# Alterar para conta de Treinamento (geralmente tipo 4)
await iq.change_balance(12345678) 
```

---

## 🔍 Exploração de Mercado e Ativos

A biblioteca carrega automaticamente a `initialization-data`, permitindo consultar o status real de qualquer ativo.

```python
# Obter status detalhado de todos os ativos Turbo
actives = await iq.get_actives("turbo")

# Verificar um ativo específico
info = iq.get_active(76) # 76 = EUR/USD
print(f"Ativo: {info.get('name')} | Aberto: {iq.is_active_open(76)}")

# Obter o Payout atual (calculado automaticamente se não disponível)
payout = iq.get_profit_percent(76)
print(f"Payout atual: {payout}%")
```

---

## 📊 Dados Históricos (Candles)

O `myiq` resolve o limite nativo de 1000 candles por requisição, permitindo buscar bases históricas gigantescas para Backtesting.

```python
from myiq.core.candle_fetcher import fetch_all_candles

# Busca 5000 velas de 1 minuto para o ativo 1
candles = await iq.fetch_candles(active_id=1, duration=60, total=5000)

for c in candles:
    print(f"Hora: {c.from_time} | Open: {c.open} | Close: {c.close}")
```

---

## 📡 Streaming em Tempo Real (Shotgun Pattern)

Para evitar que o usuário precise adivinhar se o ativo é Digital, Binary ou Blitz, o `myiq` utiliza o **Shotgun Pattern**: ele tenta se inscrever em todas as categorias simultaneamente para garantir o recebimento do stream.

```python
async def on_candle_received(candle_data):
    print(f"Vela em fechamento: {candle_data}")

# Inicia stream de 1 minuto
await iq.start_candles_stream(active_id=1, duration=60, callback=on_candle_received)
```

---

## ⚡ Execução de Trading (Blitz Options)

As ordens Blitz requerem um cálculo preciso de expiração e monitoramento de eventos `position-changed`. O método `buy_blitz` é bloqueante (assíncrono) e retorna apenas quando a operação é finalizada.

```python
# Executa uma operação de CALL de $10 com expiração de 30s
result = await iq.buy_blitz(
    active_id=1, 
    direction="call", 
    amount=10.0, 
    duration=30
)

print(f"Resultado: {result['result']} | PNL: {result['pnl']}")
```

---

## 📈 Informações Financeiras Avançadas (GraphQL)

Acesse dados profundos que geralmente só aparecem no "Asset Profile" da plataforma, como descrição da empresa, setor GICS e indicadores técnicos anuais.

```python
fin_info = await iq.get_financial_info(active_id=1)
if fin_info:
    print(f"Nome Completo: {fin_info['name']}")
    print(f"Variação Mensal (m1): {fin_info['charts']['m1']['change']}%")
```

---

## 📩 Sistema de Eventos (Dispatcher)

Você pode "plugar" funções personalizadas para ouvir qualquer evento bruto que venha do servidor da IQ Option.

```python
def log_raw_messages(msg):
    if msg.get("name") == "heartbeat":
        return
    print(f"Mensagem Bruta: {msg}")

# Adiciona um hook global no WebSocket
iq.ws.on_message_hook = log_raw_messages

# Ou um listener para um evento específico via Dispatcher
iq.dispatcher.add_listener("profile", lambda m: print("Perfil atualizado!"))
```

---

## 📋 Especificações dos Modelos (Pydantic)

### `Candle`
| Campo | Tipo | Descrição |
| :--- | :--- | :--- |
| `from_time` | `int` | Timestamp de início da vela |
| `open` / `close` | `float` | Preços de abertura e fechamento |
| `min` / `max` | `float` | Mínima e máxima do período |
| `volume` | `float` | Volume negociado |

---

## 🛠 Tratamento de Erros e Logs

A biblioteca utiliza `structlog` para logs estruturados em JSON ou Console, facilitando o debug em produção.

*   **ConnectionError**: Falha crítica de rede ou DNS.
*   **PermissionError**: Credenciais inválidas ou IP bloqueado (403).
*   **TimeoutError**: O servidor não respondeu dentro do tempo limite.

---

## ⚖️ Isenção de Responsabilidade

Este software é para fins educacionais. Negociar em opções binárias e blitz envolve alto risco. Os desenvolvedores não se responsabilizam por perdas financeiras decorrentes do uso desta biblioteca.

---

Este README cobre 100% da lógica contida nos arquivos fornecidos, desde a conexão de baixo nível até as operações de alto nível.
