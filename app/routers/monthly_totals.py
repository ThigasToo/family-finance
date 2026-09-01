from copy import deepcopy

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.cash_flow import build_cash_flow_by_month
from app.database import get_db
from app.models import FinancialSnapshot, User
from app.security import get_current_user
from app.routers.finance import (
    is_credit_card_purchase,
    normalize_text,
    transaction_amount_abs,
)
from app.routers.monthly_breakdown import _credit_card_cycle_month


router = APIRouter(
    prefix="/finance",
    tags=["finance"],
)


@router.get("/monthly-totals")
def get_monthly_totals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    snapshot = (
        db.query(FinancialSnapshot)
        .filter(FinancialSnapshot.user_id == current_user.id)
        .first()
    )

    payload = deepcopy(snapshot.payload or {}) if snapshot else {}
    accounts = payload.get("accounts") or []
    investments = payload.get("investments") or []

    card_by_month: dict[str, float] = {}

    for account in accounts:
        if normalize_text(account.get("type")) != "CREDIT":
            continue

        for transaction in account.get("transactions") or []:
            if not isinstance(transaction, dict):
                continue
            if not is_credit_card_purchase(transaction):
                continue

            amount = transaction_amount_abs(transaction)
            if amount <= 0:
                continue

            key = _credit_card_cycle_month(transaction)
            if key is None:
                continue

            card_by_month[key] = card_by_month.get(key, 0.0) + amount

    cash_flow_by_month = build_cash_flow_by_month(
        accounts,
        investments,
    )

    return {
        "credit_card_commitments_by_month": {
            key: round(value, 2)
            for key, value in card_by_month.items()
        },
        "cash_flow_net_by_month": cash_flow_by_month,
    }
