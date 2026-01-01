import asyncio
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from myiq import IQOption
try:
    from . import config
except ImportError:
    import config

EMAIL = config.EMAIL
PASSWORD = config.PASSWORD

async def debug_active():
    print(">>> Iniciando Debug de Ativo 76 (Colisão de IDs)...")
    
    iq = IQOption(EMAIL, PASSWORD)
    
    # Hook para monitorar mensagens cruas antes do parser (opcional, só para ver chegada)
    # iq.ws.on_message_hook = lambda msg: print(f"[RAW] {msg.get('name')}") if msg.get("name") == "initialization-data" else None

    print(">>> Conectando...")
    await iq.start()
    print(">>> Aguardando 'initialization-data' (Max 60s)...")
    
    found_init = False
    for i in range(30): # 30 check de 2s = 60s
        if "blitz" in iq.actives_cache or "turbo" in iq.actives_cache:
            count_blitz = len(iq.actives_cache.get("blitz", {}))
            count_turbo = len(iq.actives_cache.get("turbo", {}))
            print(f">>> [Detectado] Blitz: {count_blitz} ativos | Turbo: {count_turbo} ativos")
            if count_blitz > 0:
                print(">>> Dados de Blitz carregados!")
                found_init = True
                break
        
        await asyncio.sleep(2)
        if i % 5 == 0:
            print(f"   ... aguardando ({i*2}s)")

    if not found_init:
        print("\n[TIMEOUT] Desistindo. initialization-data não populou 'blitz' ou 'turbo'.")
    
    # Verifica o que acabou ficando no cache final (Multinível)
    print("\n[CACHE FINAL] Verificando armazenamento segregado para ID 76:")
    
    categories_to_check = ["blitz", "turbo", "binary", "digital", "digital-option"]
    found_any = False
    
    for cat in categories_to_check:
        cat_cache = iq.actives_cache.get(cat, {})
        data = cat_cache.get("76") or cat_cache.get(76)
        
        if data:
            found_any = True
            print(f" -> Categoria '{cat}':")
            print(f"    - Nome: {data.get('name')}")
            print(f"    - Enabled: {data.get('enabled')}")
            print(f"    - Suspenso: {data.get('is_suspended')}")
        else:
            print(f" -> Categoria '{cat}': Não encontrado.")

    if not found_any:
        print("\n[ALERTA] ID 76 não encontrado em NENHUMA categoria do cache.")

    await iq.close()

if __name__ == "__main__":
    asyncio.run(debug_active())
