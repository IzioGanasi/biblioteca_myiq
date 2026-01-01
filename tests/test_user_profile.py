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

async def test_user_data():
    print(">>> Iniciando Teste de Dados do Usuário (Profile, Features, Settings)...")
    
    iq = IQOption(EMAIL, PASSWORD)
    print(f">>> Logando na conta '{EMAIL}'...")
    check = await iq.start()
    
    if not check:
        print(">>> Falha na conexão.")
        return

    print(">>> Aguardando recebimento de dados (5s)...")
    await asyncio.sleep(5)

    print("\n[PROFILE DATA]")
    if iq.profile:
        print(f" - User Name: {iq.profile.get('user_name')}")
        print(f" - User ID: {iq.profile.get('user_id')}")
        print(f" - Email: {iq.profile.get('email')}")
        print(f" - Currency: {iq.profile.get('currency_char')} ({iq.profile.get('currency')})")
        print("✅ Dados de Perfil recebidos com sucesso.")
    else:
        print("❌ Dados de Perfil vazios.")

    print("\n[FEATURES]")
    if iq.features:
        print(f" - Total de Features: {len(iq.features)}")
        # Exemplo de check
        print(f" - Feature 'blitz': {iq.features.get('blitz', 'N/A')}")
        print("✅ Features recebidas.")
    else:
        print("❌ Features vazias.")

    print("\n[USER SETTINGS]")
    if iq.user_settings:
        print(f" - Total de Configurações: {len(iq.user_settings)}")
        print("✅ Configurações recebidas.")
    else:
        print(f"⚠️ User Settings vazio (pode demorar mais para receber ou depender de requisição).")

    await iq.close()

if __name__ == "__main__":
    asyncio.run(test_user_data())
