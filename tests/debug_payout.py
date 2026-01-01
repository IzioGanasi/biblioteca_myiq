import asyncio
import sys
import os
import json

# Setup de import
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from myiq import IQOption
try:
    from . import config
except ImportError:
    import config

EMAIL = config.EMAIL
PASSWORD = config.PASSWORD

async def debug_payout():
    print(">>> Conectando para verificar PAYOUT do ID 76...")
    iq = IQOption(EMAIL, PASSWORD)
    await iq.start()
    
    # Solicita dados
    await iq.ws.send({
        "name": "sendMessage", "request_id": "init_data",
        "msg": {"name": "get-initialization-data", "version": "4.0", "body": {}}
    })

    print(">>> Aguardando dados (10s)...")
    await asyncio.sleep(10)
    
    # Pega o ativo do cache Blitz
    asset = iq.check_active(76)
    
    if asset:
        print(f"\n[DADOS BRUTOS DO ATIVO 76] (Tipo: {asset.get('active_type')})")
        # Imprime chaves relevantes
        print(f" -> profit_percent (Direto): {asset.get('profit_percent')}")
        
        # Vamos ver se está escondido em 'option'
        opt = asset.get("option", {})
        print(f" -> option: {opt}")
        
        # Vamos imprimir todas as chaves para eu analisar
        print("\n=== TODAS AS CHAVES ===")
        print(list(asset.keys()))
        
        # Se profit_percent for None/0, vamos ver se algum outro ativo tem
        print("\n[COMPARATIVO COM OUTRO ATIVO BLITZ]")
        all_blitz = iq.actives_cache.get("blitz", {})
        for aid, data in all_blitz.items():
            p = data.get("profit_percent")
            if p and p > 0:
                print(f" -> Ativo {data.get('name')} ({aid}) tem Payout: {p}%")
                break
    else:
        print("❌ Ativo 76 não encontrado no cache.")

    await iq.close()

if __name__ == "__main__":
    asyncio.run(debug_payout())
