from copy import deepcopy

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.investment_transactions_client import fetch_investment_transactions
from app.models import FinancialSnapshot, User
from app.security import get_current_user


router = APIRouter(
    prefix="/finance",
    tags=["finance"],
)


@router.post("/refresh-investment-transactions")
async def refresh_investment_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    snapshot = (
        db.query(FinancialSnapshot)
        .filter(FinancialSnapshot.user_id == current_user.id)
        .first()
    )

    if snapshot is None:
        return {"status": "ok", "updated": 0}

    payload = deepcopy(snapshot.payload or {})
    investments = payload.get("investments") or []
    updated = 0

    for investment in investments:
        if not isinstance(investment, dict):
            continue

        investment_id = investment.get("id")
        if not investment_id:
            continue

        if str(investment_id).startswith("manual-"):
            continue

        try:
            transactions = await fetch_investment_transactions(
                str(investment_id)
            )
            investment["transactions"] = transactions
            updated += 1
        except Exception as exc:
            print(
                "Erro ao buscar movimentações do investimento "
                f"{investment_id}: {exc}"
            )
            investment.setdefault("transactions", [])

    payload["investments"] = investments
    snapshot.payload = payload
    db.commit()

    return {
        "status": "ok",
        "updated": updated,
    }
