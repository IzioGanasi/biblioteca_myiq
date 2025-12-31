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
                        logger.error("auth_api_error", response=data)
                else:
                    logger.error("auth_http_error", status=resp.status_code)
            except Exception as e:
                logger.error("auth_exception", error=str(e))
            return ""
