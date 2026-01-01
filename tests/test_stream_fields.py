import asyncio
import os
import sys

# Ajuste de path para pegar a versão local da lib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from myiq import IQOption, Candle, get_all_actives_status
from tests.config import EMAIL, PASSWORD

async def monitor_stream():
    iq = IQOption(EMAIL, PASSWORD)
    await iq.start()
    
    print("Conectado. Buscando ativo aberto...")
    
    # Busca ativos turbo/blitz abertos
    actives = await get_all_actives_status(iq, "turbo")
    open_active = None
    
    for aid, info in actives.items():
        if info['is_open']:
            open_active = aid
            print(f"Ativo Encontrado: {info['ticker']} (ID: {aid})")
            break
            
    if not open_active:
        print("Nenhum ativo aberto encontrado no momento. Tentando ID 76 msm assim...")
        open_active = 76

    print(f"Iniciando stream para ID {open_active}...")

    async def on_candle_update(data: dict):
        candle = Candle(**data)
        
        print(f"\n[STREAM] Candle ID: {candle.id}")
        print(f"  Ativo: {candle.active_id}")
        print(f"  Fase: {candle.phase}")
        print(f"  Preço: {candle.close}")
        print(f"  Tempo: {candle.at}")
        
    await iq.start_candles_stream(active_id=open_active, duration=60, callback=on_candle_update)
    
    # Aguarda mais tempo
    await asyncio.sleep(40)
    
    await iq.close()

if __name__ == "__main__":
    asyncio.run(monitor_stream())
