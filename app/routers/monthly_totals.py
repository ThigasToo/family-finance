from copy import deepcopy

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    FinancialSnapshot,
    MonthlyManualCommitment,
    User,
)
from app.security import get_current_user
from app.routers.finance import (
    is_credit_card_purchase,
    normalize_text,
    parse_transaction_date,
    transaction_amount_abs,
)


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

    card_by_month: dict[str, float] = {}

    for account in accounts:
        if normalize_text(account.get("type")) != "CREDIT":
            continue

        for transaction in account.get("transactions") or []:
            if not isinstance(transaction, dict):
                continue
            if not is_credit_card_purchase(transaction):
                continue

            transaction_date = parse_transaction_date(transaction)
            if transaction_date is None:
                continue

            amount = transaction_amount_abs(transaction)
            if amount <= 0:
                continue

            key = f"{transaction_date.year}-{transaction_date.month:02d}"
            card_by_month[key] = card_by_month.get(key, 0.0) + amount

    rows = (
        db.query(MonthlyManualCommitment)
        .filter(MonthlyManualCommitment.user_id == current_user.id)
        .all()
    )

    manual_by_month = {
        row.month: round(float(row.amount), 2)
        for row in rows
    }

    return {
        "credit_card_commitments_by_month": {
            key: round(value, 2)
            for key, value in card_by_month.items()
        },
        "manual_commitments_by_month": manual_by_month,
        "pix_sent_by_month": manual_by_month,
    }
