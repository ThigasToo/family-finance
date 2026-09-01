import asyncio

from app.investment_transactions_client import fetch_investment_transactions


async def ensure_investment_transactions(
    investments: list,
) -> bool:
    """Preenche movimentações ausentes com concorrência limitada."""
    pending: list[dict] = []

    for investment in investments:
        if not isinstance(investment, dict):
            continue

        investment_id = investment.get("id")
        if not investment_id:
            continue
        if str(investment_id).startswith("manual-"):
            continue
        if "transactions" in investment:
            continue

        pending.append(investment)

    if not pending:
        return False

    semaphore = asyncio.Semaphore(8)
    changed = False

    async def hydrate(investment: dict) -> None:
        nonlocal changed
        investment_id = str(investment["id"])
        try:
            async with semaphore:
                investment["transactions"] = (
                    await fetch_investment_transactions(investment_id)
                )
            changed = True
        except Exception:
            # Não grava uma lista vazia em caso de falha transitória; assim
            # uma próxima consulta ainda poderá tentar novamente.
            return

    await asyncio.gather(*(hydrate(investment) for investment in pending))
    return changed
