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

async def test_strategy_logic():
    print(">>> Iniciando Teste de Lógica da Estratégia (Mock)...")
    
    # 1. Simula o IQOption com o cache populado igual ao seu
    iq = IQOption(EMAIL, PASSWORD)
    
    # Simulação baseada na sua imagem
    iq.actives_cache["blitz"]["76"] = {
        "id": 76, "name": "front.EURUSD-OTC", "enabled": True, "is_suspended": False, "active_type": "blitz"
    }
    iq.actives_cache["binary"]["76"] = {
        "id": 76, "name": "front.EURUSD", "enabled": True, "is_suspended": True, "active_type": "binary"
    }
    
    print("\n[CENÁRIO]")
    print(" - Blitz Cache: EURUSD (76) -> ABERTO")
    print(" - Binary Cache: EURUSD (76) -> FECHADO")
    
    # 2. Lógica Antiga (Falha esperada)
    # A biblioteca corrigida NÃO permite mais acesso direto plano, requer chave intermediária
    # Mas se simulássemos um cache plano (situação antiga), falharia.
    print("\n[LÓGICA DA BIBLIOTECA]")
    
    # Agora usamos os métodos oficiais
    info = iq.check_active(76)
    
    if info:
        print(f" -> iq.check_active(76) retornou: {info.get('active_type')}")
        print(f" -> Suspenso: {info.get('is_suspended')}")
        
        if info['is_suspended'] == False and info['active_type'] == 'blitz':
            print("✅ SUCESSO: A biblioteca selecionou a versão ABERTA (Blitz)!")
        else:
            print("❌ FALHA: Selecionou a versão fechada ou errada.")
    else:
        print("❌ FALHA: Não encontrou nada.")

if __name__ == "__main__":
    asyncio.run(test_strategy_logic())
