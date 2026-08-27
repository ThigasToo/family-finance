import httpx

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from app.config import settings


PLUGGY_BASE_URL = "https://api.pluggy.ai"


_cached_api_key: str | None = None
_cached_api_key_expires_at: datetime | None = None


# =========================================================
# AUTH
# =========================================================


async def get_pluggy_api_key() -> str:
    """
    Retorna um apiKey válido da Pluggy.

    O apiKey dura aproximadamente 2 horas.
    Reutilizamos o token e renovamos antes do vencimento.
    """

    global _cached_api_key
    global _cached_api_key_expires_at

    if (
        _cached_api_key
        and _cached_api_key_expires_at
        and datetime.now(timezone.utc)
        < _cached_api_key_expires_at
    ):
        return _cached_api_key

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PLUGGY_BASE_URL}/auth",
            json={
                "clientId":
                    settings.pluggy_client_id,
                "clientSecret":
                    settings.pluggy_client_secret,
            },
        )

        response.raise_for_status()

        data = response.json()

    _cached_api_key = data[
        "apiKey"
    ]

    _cached_api_key_expires_at = (
        datetime.now(
            timezone.utc
        )
        + timedelta(
            minutes=100
        )
    )

    return _cached_api_key


# =========================================================
# CONNECT TOKEN
# =========================================================


async def create_connect_token(
    client_user_id: str,
) -> str:
    """
    Gera connectToken vinculado ao usuário
    do nosso aplicativo.
    """

    api_key = (
        await get_pluggy_api_key()
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{PLUGGY_BASE_URL}/connect_token",
            headers={
                "X-API-KEY":
                    api_key
            },
            json={
                "clientUserId":
                    client_user_id
            },
        )

        response.raise_for_status()

        return response.json()[
            "accessToken"
        ]


# =========================================================
# ITEM
# =========================================================


async def fetch_item(
    item_id: str,
) -> dict:
    """
    Busca detalhes de um Item Pluggy.
    """

    api_key = (
        await get_pluggy_api_key()
    )

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PLUGGY_BASE_URL}/items/{item_id}",
            headers={
                "X-API-KEY":
                    api_key
            },
        )

        response.raise_for_status()

        return response.json()


# =========================================================
# CONTAS
# =========================================================


async def fetch_accounts(
    item_id: str,
) -> list[dict]:
    """
    Busca contas associadas a um Item.
    """

    api_key = (
        await get_pluggy_api_key()
    )

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PLUGGY_BASE_URL}/accounts",
            headers={
                "X-API-KEY":
                    api_key
            },
            params={
                "itemId":
                    item_id
            },
        )

        response.raise_for_status()

        return response.json()[
            "results"
        ]


# =========================================================
# TRANSAÇÕES
# =========================================================


async def fetch_transactions(
    account_id: str,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    """
    Busca transações usando a API v2 da Pluggy.

    Por padrão buscamos até 12 meses de histórico.

    Também tratamos paginação por cursor.

    Parâmetros opcionais:
    - date_from
    - date_to
    """

    api_key = (
        await get_pluggy_api_key()
    )

    now = datetime.now(
        timezone.utc
    )

    # =====================================================
    # PERÍODO PADRÃO
    # =====================================================

    if date_to is None:
        date_to = now

    if date_from is None:
        date_from = (
            date_to
            - timedelta(
                days=365
            )
        )

    # =====================================================
    # NORMALIZA TIMEZONE
    # =====================================================

    if date_from.tzinfo is None:
        date_from = (
            date_from.replace(
                tzinfo=timezone.utc
            )
        )

    if date_to.tzinfo is None:
        date_to = (
            date_to.replace(
                tzinfo=timezone.utc
            )
        )

    # =====================================================
    # PARAMS
    # =====================================================

    params = {
        "accountId":
            account_id,

        "dateFrom":
            date_from
            .date()
            .isoformat(),

        "dateTo":
            date_to
            .date()
            .isoformat(),

        "pageSize":
            500,
    }

    all_transactions = []

    cursor = None

    async with httpx.AsyncClient() as client:

        while True:

            current_params = dict(
                params
            )

            if cursor:
                current_params[
                    "cursor"
                ] = cursor

            response = await client.get(
                f"{PLUGGY_BASE_URL}/v2/transactions",
                headers={
                    "X-API-KEY":
                        api_key
                },
                params=
                    current_params,
            )

            response.raise_for_status()

            data = response.json()

            # =================================================
            # RESULTADOS
            # =================================================

            results = (
                data.get(
                    "results"
                )
                or []
            )

            all_transactions.extend(
                results
            )

            # =================================================
            # PRÓXIMO CURSOR
            # =================================================

            cursor = data.get(
                "next"
            )

            if not cursor:
                break

    return all_transactions


# =========================================================
# INVESTIMENTOS
# =========================================================


async def fetch_investments(
    item_id: str,
) -> list[dict]:
    """
    Busca investimentos associados a um Item.
    """

    api_key = (
        await get_pluggy_api_key()
    )

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PLUGGY_BASE_URL}/investments",
            headers={
                "X-API-KEY":
                    api_key
            },
            params={
                "itemId":
                    item_id
            },
        )

        response.raise_for_status()

        return response.json()[
            "results"
        ]