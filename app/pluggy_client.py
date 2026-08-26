import httpx
from datetime import datetime, timedelta, timezone
from app.config import settings

PLUGGY_BASE_URL = "https://api.pluggy.ai"

_cached_api_key: str | None = None
_cached_api_key_expires_at: datetime | None = None


async def get_pluggy_api_key() -> str:
    """Retorna um apiKey válido, reaproveitando o cache quando possível."""
    global _cached_api_key, _cached_api_key_expires_at

    if _cached_api_key and _cached_api_key_expires_at and datetime.now(timezone.utc) < _cached_api_key_expires_at:
        return _cached_api_key

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PLUGGY_BASE_URL}/auth",
            json={
                "clientId": settings.pluggy_client_id,
                "clientSecret": settings.pluggy_client_secret,
            },
        )
        response.raise_for_status()
        data = response.json()

    _cached_api_key = data["apiKey"]
    # O apiKey da Pluggy dura ~2h; renovamos com folga a cada 100 min
    _cached_api_key_expires_at = datetime.now(timezone.utc) + timedelta(minutes=100)
    return _cached_api_key


async def create_connect_token(client_user_id: str) -> str:
    """Gera um connectToken vinculado a um usuário específico do nosso app."""
    api_key = await get_pluggy_api_key()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PLUGGY_BASE_URL}/connect_token",
            headers={"X-API-KEY": api_key},
            json={"clientUserId": client_user_id},
        )
        response.raise_for_status()
        return response.json()["accessToken"]


async def fetch_item(item_id: str) -> dict:
    """Busca detalhes de um item (status da conexão, instituição etc.)."""
    api_key = await get_pluggy_api_key()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PLUGGY_BASE_URL}/items/{item_id}",
            headers={"X-API-KEY": api_key},
        )
        response.raise_for_status()
        return response.json()

async def fetch_accounts(item_id: str) -> list[dict]:
    api_key = await get_pluggy_api_key()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PLUGGY_BASE_URL}/accounts",
            headers={"X-API-KEY": api_key},
            params={"itemId": item_id},
        )
        response.raise_for_status()
        return response.json()["results"]


async def fetch_transactions(account_id: str) -> list[dict]:
    api_key = await get_pluggy_api_key()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PLUGGY_BASE_URL}/transactions",
            headers={"X-API-KEY": api_key},
            params={"accountId": account_id, "pageSize": 500},
        )
        response.raise_for_status()
        return response.json()["results"]


async def fetch_investments(item_id: str) -> list[dict]:
    api_key = await get_pluggy_api_key()
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PLUGGY_BASE_URL}/investments",
            headers={"X-API-KEY": api_key},
            params={"itemId": item_id},
        )
        response.raise_for_status()
        return response.json()["results"]