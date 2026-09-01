import httpx

from app.pluggy_client import get_pluggy_api_key


PLUGGY_BASE_URL = "https://api.pluggy.ai"


async def fetch_investment_transactions(
    investment_id: str,
) -> list[dict]:
    """Busca todas as movimentações de um investimento na Pluggy."""

    api_key = await get_pluggy_api_key()
    page = 1
    page_size = 500
    all_transactions: list[dict] = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            response = await client.get(
                f"{PLUGGY_BASE_URL}/investments/{investment_id}/transactions",
                headers={"X-API-KEY": api_key},
                params={
                    "page": page,
                    "pageSize": page_size,
                },
            )

            if response.status_code == 404:
                return []

            response.raise_for_status()
            data = response.json()
            results = data.get("results") or []

            all_transactions.extend(
                transaction
                for transaction in results
                if isinstance(transaction, dict)
            )

            total = data.get("total")
            total_pages = data.get("totalPages")

            if total_pages is not None:
                try:
                    if page >= int(total_pages):
                        break
                except (TypeError, ValueError):
                    pass

            if total is not None:
                try:
                    if page * page_size >= int(total):
                        break
                except (TypeError, ValueError):
                    pass

            if len(results) < page_size:
                break

            page += 1

            # Proteção para respostas inconsistentes da API.
            if page > 20:
                break

    return all_transactions
