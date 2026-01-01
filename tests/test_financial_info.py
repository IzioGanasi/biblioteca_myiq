import asyncio
import sys
import os
import argparse

# Adiciona o diretório raiz ao path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from myiq import IQOption
try:
    from . import config
except ImportError:
    import config

EMAIL = config.EMAIL
PASSWORD = config.PASSWORD

async def test_financial_info(active_id):
    print(f">>> Iniciando Teste de Financial Info para Ativo ID: {active_id}...")
    
    iq = IQOption(EMAIL, PASSWORD)
    check = await iq.start()
    
    if not check:
        print(">>> Falha na conexão.")
        return

    print(f">>> Solicitando dados financeiros (GraphQL)...")
    info = await iq.get_financial_info(active_id)
    
    if info:
        print("\n[FINANCIAL INFO START]")
        print(f"ID: {info.get('id')}")
        print(f"Name: {info.get('name')}")
        print(f"Ticker: {info.get('ticker')}")
        
        fininfo = info.get('fininfo')
        if fininfo:
            pair = fininfo[0] if isinstance(fininfo, list) else fininfo
            print(f"Descrição: {pair.get('description')}")
            base = pair.get('base', {})
            print(f"Base Name: {base.get('name')}")
            
            # Dados específicos
            if "company" in base:
                print(f"Empresa: {base['company'].get('nameShort')}")
            if "coinsInCirculation" in base:
                print(f"Circulação: {base.get('coinsInCirculation')}")
        
        print("[FINANCIAL INFO END]")
    else:
        print("❌ Não foi possível obter dados (Timeout ou Erro).")

    await iq.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, default=76, help="Active ID to query")
    args = parser.parse_args()
    
    asyncio.run(test_financial_info(args.id))
