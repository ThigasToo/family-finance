from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx

from app.config import settings


PLUGGY_BASE_URL = "https://api.pluggy.ai"
REQUEST_TIMEOUT = 60.0

_cached_api_key: str | None = None
_cached_api_key_expires_at: datetime | None = None


async def get_pluggy_api_key() -> str:
    global _cached_api_key
    global _cached_api_key_expires_at

    if (
        _cached_api_key
        and _cached_api_key_expires_at
        and datetime.now(timezone.utc) < _cached_api_key_expires_at
    ):
        return _cached_api_key

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
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
    _cached_api_key_expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=100
    )
    return _cached_api_key


async def create_connect_token(client_user_id: str) -> str:
    api_key = await get_pluggy_api_key()

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(
            f"{PLUGGY_BASE_URL}/connect_token",
            headers={"X-API-KEY": api_key},
            json={"clientUserId": client_user_id},
        )
        response.raise_for_status()
        return response.json()["accessToken"]


async def fetch_item(item_id: str) -> dict:
    api_key = await get_pluggy_api_key()

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(
            f"{PLUGGY_BASE_URL}/items/{item_id}",
            headers={"X-API-KEY": api_key},
        )
        response.raise_for_status()
        return response.json()


async def fetch_accounts(item_id: str) -> list[dict]:
    api_key = await get_pluggy_api_key()

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(
            f"{PLUGGY_BASE_URL}/accounts",
            headers={"X-API-KEY": api_key},
            params={"itemId": item_id},
        )
        response.raise_for_status()
        return response.json().get("results") or []


def _extract_after_cursor(next_value) -> str | None:
    if not next_value:
        return None

    if isinstance(next_value, dict):
        after = next_value.get("after")
        return str(after) if after else None

    value = str(next_value).strip()
    if not value:
        return None

    if "after=" in value:
        parsed = urlparse(value)
        values = parse_qs(parsed.query).get("after")
        if values:
            return values[0]

        values = parse_qs(value.lstrip("?")).get("after")
        if values:
            return values[0]

    if "?" not in value and "=" not in value:
        return value

    return None


async def fetch_transactions(
    account_id: str,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    api_key = await get_pluggy_api_key()
    now = datetime.now(timezone.utc)

    if date_to is None:
        date_to = now
    if date_from is None:
        date_from = date_to - timedelta(days=365)

    if date_from.tzinfo is None:
        date_from = date_from.replace(tzinfo=timezone.utc)
    if date_to.tzinfo is None:
        date_to = date_to.replace(tzinfo=timezone.utc)

    params = {
        "accountId": account_id,
        "dateFrom": date_from.date().isoformat(),
        "dateTo": date_to.date().isoformat(),
    }

    all_transactions: list[dict] = []
    after: str | None = None
    seen_cursors: set[str] = set()

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        while True:
            current_params = dict(params)
            if after:
                current_params["after"] = after

            response = await client.get(
                f"{PLUGGY_BASE_URL}/v2/transactions",
                headers={"X-API-KEY": api_key},
                params=current_params,
            )
            response.raise_for_status()
            data = response.json()

            results = data.get("results") or []
            all_transactions.extend(
                transaction
                for transaction in results
                if isinstance(transaction, dict)
            )

            next_after = _extract_after_cursor(data.get("next"))
            if not next_after or next_after in seen_cursors:
                break

            seen_cursors.add(next_after)
            after = next_after

    return all_transactions


async def fetch_investments(item_id: str) -> list[dict]:
    api_key = await get_pluggy_api_key()

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(
            f"{PLUGGY_BASE_URL}/investments",
            headers={"X-API-KEY": api_key},
            params={"itemId": item_id},
        )
        response.raise_for_status()
        return response.json().get("results") or []
