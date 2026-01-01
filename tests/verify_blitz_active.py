import asyncio
import os
from myiq.core.client import IQOption

async def main():
    email = "izio.silva@outlook.com"
    password = "M@noEch!0"
    
    if not email or not password:
        print("Defina IQ_EMAIL e IQ_PASSWORD no ambiente.")
        return

    iq = IQOption(email, password)
    try:
        await iq.start()
        print("Autenticado.")
        
        # 1. Carregar/Atualizar dados dos ativos (Turbo contém Blitz geralmente)
        print("Atualizando lista de ativos...")
        await iq.get_actives("turbo") 
        
        # ID de exemplo (MANAUSD-OTC - 2163) ou podemos buscar um específico
        # Vamos listar alguns ativos "abertos"
        
        target_ids = [2163, 76] # MANAUSD-OTC e Uranium (exemplo anterior)
        
        for active_id in target_ids:
            # Uso nativo dos novos métodos
            status = iq.check_active(active_id)
            is_open = iq.is_active_open(active_id)
            profit = iq.get_profit_percent(active_id)
            
            if not status:
                print(f"Ativo {active_id} não encontrado na lista 'turbo'.")
                continue
                
            print(f"--- Ativo {active_id} ({status.get('name')}) ---")
            print(f"  Esta aberto? {'SIM' if is_open else 'NAO'}")
            print(f"  Profit: {profit}%")
            print(f"  Detalhes: Enabled={status['enabled']}, Suspended={status['suspended']}, MarketOpen={status['market_open']}")
            print("-" * 30)
            
    except Exception as e:
        print(f"Erro: {e}")
    finally:
        await iq.close()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(main())
