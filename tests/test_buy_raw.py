import asyncio
import json
import time
import sys
import os

# Force usage of local myiq package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from myiq import IQOption

async def test_buy_native(email, password):
    iq = IQOption(email, password)
    print("Connecting...")
    await iq.start()
    
    # 1. Start Initialization Data (Important for Payout Cache)
    # The client method buy_blitz uses get_profit_percent internally
    # We should ensure cache is populated
    print("Populating cache with initialization-data...")
    await iq.get_actives("turbo")
    
    # 2. Select Balance
    balances = await iq.get_balances()
    practice_balance = next((b for b in balances if b.type == 4), None)
    
    if practice_balance:
        print(f"Practice balance selected: {practice_balance.id}")
        await iq.change_balance(practice_balance.id)
    else:
        print("No practice balance found.")
        await iq.close()
        return

    # 3. Validar lucro antes 
    active_id = 76 # EURUSD
    profit = iq.get_profit_percent(active_id)
    print(f"Active {active_id} Payout: {profit}%")

    if profit == 0:
        print("Erro: Payout zerado ou ativo fechado.")
        await iq.close()
        return

    # 4. Executar Compra via Biblioteca
    print("Executando buy_blitz via Lib High-Level...")
    try:
        # Usando amount=10 para evitar rejeição mínima(1.0)
        # Duration 30s
        result = await iq.buy_blitz(active_id=active_id, direction="call", amount=10, duration=30)
        
        print("\n--- TRADE RESULT ---")
        print(json.dumps(result, indent=2))
        
        if result.get("status") == "closed":
            pnl = result.get("pnl", 0)
            print(f"Trade Finished! PnL: {pnl}")
        else:
            print("Trade failed or timed out.")
            
    except Exception as e:
        print(f"Exception during trade: {e}")

    await iq.close()

if __name__ == "__main__":
    from tests.config import EMAIL, PASSWORD
    asyncio.run(test_buy_native(EMAIL, PASSWORD))
