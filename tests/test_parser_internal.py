import sys
import os
import unittest
# Adiciona o diretório raiz ao path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from myiq import IQOption

class TestParserInternal(unittest.TestCase):
    def test_initialization_data_parsing(self):
        print("\n>>> Iniciando Teste Simulado de Parsing (Sem Conexão)...")
        
        # 1. Instancia dummy (sem conectar)
        iq = IQOption("dummy", "dummy")
        
        # 2. Mock da mensagem initialization-data (Simplificada)
        # O ponto crítico: garantir que chaves diferentes ('turbo' e 'binary')
        # guardem informações concorrentes para o mesmo ID ('76').
        mock_msg = {
            "name": "initialization-data",
            "msg": {
                "turbo": {
                    "actives": {
                        "76": {
                            "id": 76, 
                            "name": "front.EURUSD-OTC", 
                            "enabled": True, 
                            "is_suspended": False # ABERTO
                        }
                    }
                },
                "binary": {
                    "actives": {
                        "76": {
                            "id": 76, 
                            "name": "front.EURUSD", 
                            "enabled": True, 
                            "is_suspended": True # FECHADO
                        }
                    }
                },
                "blitz": {
                    "actives": {
                         "2144": {
                             "id": 2144,
                             "name": "front.WIFUSD-OTC",
                             "enabled": True
                         }
                    }
                }
            }
        }
        
        # 3. Executa o parser manualmente
        print("[PROCESSANDO] Enviando mensagem mock para _on_initialization_data...")
        iq._on_initialization_data(mock_msg)
        
        # 4. Verifica o cache
        # Esperado: 
        # iq.actives_cache["turbo"]["76"] exist e suspenso=False
        # iq.actives_cache["binary"]["76"] exist e suspenso=True
        
        turbo_76 = iq.actives_cache.get("turbo", {}).get("76")
        binary_76 = iq.actives_cache.get("binary", {}).get("76")
        blitz_asset = iq.actives_cache.get("blitz", {}).get("2144")
        
        if turbo_76 and binary_76:
            print(f" -> Turbo 76: Suspenso={turbo_76.get('is_suspended')}")
            print(f" -> Binary 76: Suspenso={binary_76.get('is_suspended')}")
            
            if turbo_76['is_suspended'] != binary_76['is_suspended']:
                print("🏆 CONCLUSÃO: O problema foi resolvido!")
                print("   O cache armazenou estados DEFERENTES para o mesmo ID em categorias diferentes.")
            else:
                print("❌ FALHA: Estados iguais (colisão não resolvida).")
        else:
            print("❌ FALHA: Ativos não encontrados no cache.")
            
        if blitz_asset:
            print("✅ Blitz asset 2144 encontrado corretamente.")

if __name__ == "__main__":
    unittest.main()
