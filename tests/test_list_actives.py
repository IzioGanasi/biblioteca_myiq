import asyncio
import json
import time
import sys
import os

# Force usage of local myiq package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import myiq
from myiq import IQOption

async def list_blitz_actives(email, password):
    iq = IQOption(email, password)
    
    init_future = asyncio.get_running_loop().create_future()
    
    def catch_init(msg):
        if msg.get("name") == "initialization-data":
            if not init_future.done():
                init_future.set_result(msg)

    iq.dispatcher.add_listener("initialization-data", catch_init)
    
    print("Conectando e aguardando initialization-data...")
    await iq.start()
    
    # Explicitly request initialization data
    from myiq.core.utils import get_req_id
    print("Solicitando dados de inicialização...")
    await iq.ws.send({
        "name": "sendMessage",
        "request_id": get_req_id(),
        "msg": {
            "name": "get-initialization-data",
            "version": "4.0",
            "body": {}
        }
    })
    
    try:
        raw_init = await asyncio.wait_for(init_future, timeout=30.0)
        msg_content = raw_init.get("msg", {})
        
        # Tenta obter o horário do servidor para validar schedules
        server_time = iq.get_server_timestamp()
        if server_time == 0:
             # Fallback se não tiver sincronizado
             server_time = int(time.time() * 1000)

        print(f"\nHorário do Servidor (ref): {server_time}")
        print("\n--- ATIVOS ENCONTRADOS NO MODO TURBO (BLITZ) ---")
        print(f"{'ID':<10} | {'Ticker':<20} | {'Status':<10} | {'Profit %':<10} | {'Aberto?':<10}")
        print("-" * 75)
        
        turbo_data = msg_content.get("turbo", {})
        actives_dict = turbo_data.get("actives", {})
        
        count = 0
        # Ordenar por nome para facilitar leitura
        sorted_actives = sorted(actives_dict.items(), key=lambda x: x[1].get("name", ""))

        for active_id, info in sorted_actives:
            name = info.get("name", "N/A")
            is_enabled = info.get("enabled", False)
            is_suspended = info.get("is_suspended", False)
            
            # Cálculo de Profit (Commission)
            # Estrutura típica: option -> profit -> commission
            commission = info.get("option", {}).get("profit", {}).get("commission", 0)
            profit_percent = 100 - commission if commission > 0 else 0

            # Validação de Horário (Schedule)
            schedule = info.get("schedule", [])
            is_market_open = False
            if schedule:
                for start, end in schedule:
                    if start <= server_time <= end:
                        is_market_open = True
                        break
            
            # Status final
            is_truly_open = is_enabled and not is_suspended and is_market_open
            
            status_str = "OPEN" if is_truly_open else "CLOSED"
            if is_suspended:
                status_str = "SUSPENDED"
            elif not is_market_open and is_enabled:
                status_str = "OFF-HOURS"

            # Exibir apenas se estiver habilitado ou aberto (reduzir ruído)
            # Mas se quiser ver tudo, comente o if abaixo.
            if not is_enabled and not is_market_open:
                continue

            print(f"{str(active_id):<10} | {name:<20} | {status_str:<10} | {str(profit_percent)+'%':<10} | {str(is_truly_open):<10}")
            count += 1
            
        if count == 0:
            print("Nenhum ativo 'ativo' encontrado na categoria 'turbo'.")
            print("Verifique se estamos no horário de negociação ou se a conta suporta.")

    except asyncio.TimeoutError:
        print("Timeout: Não recebemos o initialization-data a tempo.")
    except Exception as e:
        print(f"Erro ao processar dados: {e}")
    
    await iq.close()

if __name__ == "__main__":
    from tests.config import EMAIL, PASSWORD
    asyncio.run(list_blitz_actives(EMAIL, PASSWORD))
