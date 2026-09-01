import asyncio

from app.investment_transactions_client import fetch_investment_transactions


async def ensure_investment_transactions(
    investments: list,
) -> bool:
    """Preenche transactions dos investimentos quando ainda não foram salvos.

    Faz as consultas em paralelo com concorrência limitada para evitar
    uma primeira carga lenta quando o usuário possui muitos investimentos.
    Retorna True quando o payload foi alterado.
    """
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

    async def hydrate(investment: dict) -> None:
        investment_id = str(investment["id"])
        try:
            async with semaphore:
                investment["transactions"] = (
                    await fetch_investment_transactions(investment_id)
                )
        except Exception as exc:
            print(
                "Erro ao preencher movimentações do investimento "
                f"{investment_id}: {exc}"
            )
            investment["transactions"] = []

    await asyncio.gather(*(hydrate(investment) for investment in pending))
    return True
