# IQ Option ML Trader Library

Este projeto fornece uma biblioteca Python para comunicação com a API da IQ Option, permitindo a obtenção de candles, balances e execução de trades Blitz.

## Instalação
1. Instale via git
```bash
pip install git+https://github.com/IzioGanasi/biblioteca_myiq.git
```
ou via Pypi
```bash
pip install myiq
```
2. Certifique-se de ter o Python instalado (recomendado 3.10+).
2. Instale as dependências:

```bash
pip install -r requirements.txt
```

## Uso Básico

```python
import asyncio
from myiq import IQOption

async def main():
    # Configure suas credenciais em variáveis de ambiente ou arquivo seguro
    email = "seu_email" 
    senha = "sua_senha"
    
    iq = IQOption(email, senha)
    await iq.start()
    
    balances = await iq.get_balances()
    print(balances)
    
    candles = await iq.fetch_candles(active_id=76, duration=60, total=1500)
    print(f"[candles] Received {len(candles)} candles")
    
    await iq.close()

asyncio.run(main())
```

## Exemplos de Cada Módulo

### 1. Autenticação HTTP (`IQAuth`)
```python
from myiq import IQAuth
import asyncio

async def demo_auth():
    auth = IQAuth("email", "senha")
    ssid = await auth.get_ssid()
    print("SSID:", ssid)

asyncio.run(demo_auth())
```

### 2. Cliente Core (`IQOption`)
```python
from myiq import IQOption
import asyncio

async def demo_client():
    iq = IQOption("email", "senha")
    await iq.start()
    
    # Listar ativos abertos no momento para Blitz
    actives = await iq.get_actives("turbo")
    for id, info in actives.items():
        if info['open']:
            print(f"Ativo {info['name']} (ID: {id}) disponível")
            
    await iq.close()

asyncio.run(demo_client())
```

### 3. Utilitários
```python
from myiq import get_req_id, get_sub_id, get_client_id

print("req_id:", get_req_id())
print("sub_id:", get_sub_id())
print("client_id:", get_client_id())
```

### 4. Dispatcher e Eventos
```python
from myiq import IQOption
import asyncio

async def demo_dispatcher():
    iq = IQOption("email", "senha")
    await iq.start()
    
    def on_candle(msg):
        print("Nova vela gerada:", msg)
        
    iq.dispatcher.add_listener("candle-generated", on_candle)
    await iq.start_candles_stream(active_id=76, duration=60, callback=lambda d: None)
    
    await asyncio.sleep(10)
    await iq.close()

asyncio.run(demo_dispatcher())
```

### 5. Modelos Pydantic
```python
from myiq import Balance, Candle

raw_balance = {"id": 123, "type": 4, "amount": 100.0, "currency": "USD"}
balance = Balance(**raw_balance)
print(balance)
```

## Raw WebSocket Return Dictionaries

### Balance
```json
{
  "id": 123,
  "type": 4,
  "amount": 100.0,
  "currency": "USD"
}
```

### Candle
```json
{
  "id": 1,
  "from": 1700000000,
  "to": 1700000060,
  "open": 1.1234,
  "close": 1.1240,
  "min": 1.1220,
  "max": 1.1250,
  "volume": 2500.0
}
```

## Estrutura do Projeto

- `myiq/`: Core da biblioteca.
  - `core/`: Clientes, conexão, reconexão e descoberta de ativos.
  - `http/`: Autenticação.
  - `models/`: Modelos de dados.
- `requirements.txt`: Dependências.
- `pyproject.toml`: Configuração de build (PyPI).

## Licença
MIT
