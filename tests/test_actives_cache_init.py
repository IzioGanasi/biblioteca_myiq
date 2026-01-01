import asyncio
import sys
import os

# Adiciona o diretório raiz ao path para importar myiq
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from myiq import IQOption
try:
    from . import config
except ImportError:
    import config

EMAIL = config.EMAIL
PASSWORD = config.PASSWORD

async def test_actives_cache_init():
    print(">>> Iniciando Teste de Inicialização do Cache de Ativos...")
    
    iq = IQOption(EMAIL, PASSWORD)
    print(f">>> Logando na conta '{EMAIL}'...")
    check = await iq.start()
    
    if check:
        print(">>> Conectado com sucesso!")
    else:
        print(">>> Falha na conexão.")
        return

    iq.subscribe_actives()
    
    # Aguarda tempo suficiente para receber initialization-data (pode demorar +10s em contas grandes)
    print(">>> Aguardando recebimento de Initialization Data e Listas (5s)...")
    await asyncio.sleep(5)

    total_actives = sum(len(v) for v in iq.actives_cache.values())
    print(f"\n[CACHE] Total de ativos cacheados (todas categorias): {total_actives}")

    if total_actives == 0:
        print("ALERTA: Cache vazio! O parser de initialization-data ou underlying-list falhou.")
    else:
        print("SUCESSO: Cache populado.")
        
        # Teste de amostragem por categoria
        print("\n[DETALHES DA CATEGORIA]")
        
        # Priorizar mostrar Blitz primeiro se existir
        preferred_order = ["blitz", "turbo", "binary", "digital"]
        existing_keys = list(iq.actives_cache.keys())
        # Ordena para mostrar prioritárias primeiro
        existing_keys.sort(key=lambda x: preferred_order.index(x) if x in preferred_order else 99)
        
        for category in existing_keys:
            actives_dict = iq.actives_cache[category]
            print(f" -> Categoria: '{category}' com {len(actives_dict)} ativos.")
            
            # Amostra de 3 ativos dessa categoria
            sample = list(actives_dict.values())[:3]
            for s in sample:
                a_id = s.get("id") or s.get("active_id")
                name = s.get("name") or s.get("ticker", "N/A")
                suspended = s.get("is_suspended", "N/A")
                print(f"    - ID: {a_id} | Nome: {name} | Suspenso: {suspended}")

    await iq.close()

if __name__ == "__main__":
    asyncio.run(test_actives_cache_init())
