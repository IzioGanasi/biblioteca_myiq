import httpx
import structlog

logger = structlog.get_logger()

class IQAuth:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password

    async def get_ssid(self) -> str:
        async with httpx.AsyncClient() as client:
            payload = {"identifier": self.email, "password": self.password}
            try:
                resp = await client.post("https://auth.iqoption.com/api/v2/login", json=payload)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("code") == "success":
                        return data.get("ssid", "")
                    else:
                        # API retornou 200 mas com erro no corpo (ex: 2FA required, etc)
                        msg = data.get("message") or str(data)
                        logger.error("auth_api_error", response=data)
                        raise ValueError(f"Erro na API de autenticação: {msg}")

                elif resp.status_code == 400:
                     # Geralmente dados inválidos no request
                    logger.error("auth_bad_request", response=resp.text)
                    raise ValueError("Requisição inválida (400). Verifique formato do email/senha.")

                elif resp.status_code == 401:
                    # Credenciais erradas
                    logger.error("auth_unauthorized")
                    raise PermissionError("Credenciais inválidas (401). Verifique email e senha.")

                elif resp.status_code == 403:
                    # Bloqueio de IP ou WAF (Cloudflare etc)
                    logger.error("auth_forbidden")
                    raise PermissionError("Acesso negado (403). Seu IP pode estar bloqueado ou restrito pela corretora.")

                elif resp.status_code == 429:
                    logger.error("auth_rate_limit")
                    raise ConnectionError("Muitas tentativas de login (429). Aguarde alguns minutos.")

                else:
                    logger.error("auth_http_error", status=resp.status_code)
                    raise ConnectionError(f"Erro HTTP desconhecido na autenticação: {resp.status_code}")

            except httpx.RequestError as e:
                logger.error("auth_network_error", error=str(e))
                raise ConnectionError(f"Erro de conexão ao tentar fazer login: {str(e)}")
            except Exception as e:
                # Se já for uma das exceções que levantamos acima, só deixa passar
                if isinstance(e, (ValueError, PermissionError, ConnectionError)):
                    raise
                logger.error("auth_exception", error=str(e))
                raise RuntimeError(f"Erro inesperado no login: {str(e)}")
