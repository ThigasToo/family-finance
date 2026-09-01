from app.investment_transactions_client import fetch_investment_transactions


async def ensure_investment_transactions(
    investments: list,
) -> bool:
    """Preenche transactions dos investimentos quando ainda não foram salvos.

    Retorna True quando o payload foi alterado.
    """
    changed = False

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

        try:
            investment["transactions"] = (
                await fetch_investment_transactions(str(investment_id))
            )
        except Exception as exc:
            print(
                "Erro ao preencher movimentações do investimento "
                f"{investment_id}: {exc}"
            )
            investment["transactions"] = []

        changed = True

    return changed
