import asyncio
import httpx
import json

async def test_auth_raw(email, password):
    async with httpx.AsyncClient() as client:
        payload = {"identifier": email, "password": password}
        print(f"--- POST Request to https://auth.iqoption.com/api/v2/login ---")
        resp = await client.post("https://auth.iqoption.com/api/v2/login", json=payload)
        
        print(f"Status Code: {resp.status_code}")
        data = resp.json()
        print("\n--- RAW JSON RESPONSE ---")
        print(json.dumps(data, indent=2))
        return data

if __name__ == "__main__":
    from tests.config import EMAIL, PASSWORD
    asyncio.run(test_auth_raw(EMAIL, PASSWORD))
