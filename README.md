# Biblioteca myiq

Uma biblioteca Python moderna, assíncrona e robusta para interação com a plataforma de negociação IQ Option. Projetada para estabilidade, performance e facilidade de uso em projetos de Trading Algorítmico e Machine Learning.

**Status:** v0.1.2 Stable

## Funcionalidades Principais

- **Conexão Assíncrona:** Baseada em `asyncio` e `websockets`, permitindo alta concorrência.
- **Reconexão Automática:** Sistema nativo de `ReconnectingWS` que mantém a sessão ativa e recupera quedas de rede transparentemente.
- **Gestão de Ativos:** Ferramentas completas para descobrir ativos abertos/fechados, lucro (payout) e horários.
- **Dados Históricos e Tempo Real:** Coleta massiva de candles históricos e streaming de velas em tempo real com baixa latência.
- **Trading:** Execução de ordens Blitz e Digitais.

## Instalação

Direto do PyPI:
```bash
pip install myiq
```

Ou a versão mais recente do GitHub:
```bash
pip install git+https://github.com/IzioGanasi/biblioteca_myiq.git
```

Dependências básicas: `aiohttp`, `websockets`, `pydantic`, `structlog`.

---

## Guia Completo de Funcionalidades

Abaixo listamos como utilizar **cada uma** das funcionalidades disponíveis na biblioteca.

### 1. Inicialização e Conexão

A classe `IQOption` gerencia tudo. O método `start()` realiza o login HTTP e estabelece o WebSocket.

```python
import asyncio
from myiq import IQOption

async def main():
    iq = IQOption("email@exemplo.com", "senha123")
    
    # Inicia conexão e loop de autenticação
    await iq.start()
    print("Conectado com sucesso!")
    
    # ... operações ...
    
    await iq.close()

asyncio.run(main())
```

### 2. Gerenciamento de Conta (Balances)

Liste seus saldos (Real, Practice/Demo, Torneio) e troque entre eles.

```python
# Listar todos os saldos disponíveis
balances = await iq.get_balances()
print("Saldos disponíveis:", balances)

# Trocar para conta de Prática (procure o ID type=4 geralmente)
# Exemplo: Encontrar e mudar para saldo de treino
for b in balances:
    if b.type == 4:  # 1=Real, 4=Practice
        print(f"Mudando para saldo de treino: {b.amount}")
        await iq.change_balance(b.id)
        break
```

### 3. Mapeador de Ativos (Actives Explorer)

Descubra quais ativos estão operáveis **agora**, seus payouts e status de suspensão. Esta é a funcionalidade mais avançada para filtrar o mercado.

```python
from myiq import get_all_actives_status

# Retorna um dicionário completo com status de cada ativo 'turbo'
# Chave = Active ID
actives = await get_all_actives_status(iq, instrument_type="turbo")

print("Ativos Abertos e com Lucro > 80%:")
for active_id, info in actives.items():
    if info['is_open'] and info['profit_percent'] >= 80:
        print(f"ID: {active_id} | Nome: {info['ticker']} | Payout: {info['profit_percent']}%")

# info contém: 'enabled', 'suspended', 'market_open', 'schedule', 'image', etc.
```

Métodos auxiliares rápidos no cliente:
```python
# Checagem rápida de um ativo específico
status = await iq.check_active(76) # 76 = EURUSD
print(f"EURUSD Aberto? {iq.is_active_open(76)}")
print(f"Payout atual: {iq.get_profit_percent(76)}%")
```

### 4. Coleta de Candles (Histórico)

Baixe milhares de velas automaticamente. A função lida com a paginação interna da IQ Option.

```python
# Baixa 1000 velas de 1 minuto (60s) do ativo 76 (EURUSD)
candles = await iq.fetch_candles(active_id=76, duration=60, total=1000)

print(f"Baixadas {len(candles)} velas.")
print(f"Primeira: {candles[0]}")
print(f"Última: {candles[-1]}")
```

### 5. Candles em Tempo Real (Streaming)

Receba velas assim que elas fecham ou atualizam, ideal para bots que operam tick-a-tick.

```python
def on_new_candle(candle_data):
    print(f"Nova atualização de vela: {candle_data}")

# Assina o ativo 76 para velas de 1 minuto
# O callback é chamado a cada atualização
await iq.start_candles_stream(active_id=76, duration=60, callback=on_new_candle)

# Mantenha o loop rodando para continuar recebendo
await asyncio.sleep(60)
```

### 6. Execução de Ordens (Trading)

Envie ordens de compra (Call/Put). Atualmente suporta opções Blitz/Turbo.

```python
# Compra de $10, direção CALL, expiração 30s (padrão blitz) no ativo 76
await iq.buy_blitz(active_id=76, direction="call", amount=10, duration=30)

# Para saber o resultado, você deve ouvir os eventos de 'order-created' ou consultar histórico.
# O método buy_blitz envia a ordem, o processamento é assíncrono.
```

### 7. Sistema de Eventos (Dispatcher)

Para usuários avançados que querem ouvir eventos crus do WebSocket (ex: resultados de portfolio, mudanças de saldo).

```python
def debug_listener(msg):
    if msg.get("name") == "position-changed":
        print("Posição alterada!", msg)

iq.dispatcher.add_listener("position-changed", debug_listener)
```

## Estrutura de Diretórios

```
myiq/
├── core/           # Lógica principal (Client, WebSocket, Reconnect)
├── http/           # Autenticação HTTP (SSID)
├── models/         # Definições de dados (Candle, Balance)
└── utils/          # Funções auxiliares
```

## Contribuindo

Pull Requests são bem-vindos. Para mudanças maiores, abra uma issue primeiro para discutir o que você gostaria de mudar.

## Licença

[MIT](https://choosealicense.com/licenses/mit/)
