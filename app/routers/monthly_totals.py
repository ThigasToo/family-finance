from copy import deepcopy

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FinancialSnapshot, User
from app.security import get_current_user
from app.routers.finance import (
    is_credit_card_purchase,
    is_outflow_transaction,
    is_pix_transaction,
    normalize_text,
    parse_transaction_date,
    transaction_amount_abs,
)
from app.routers.monthly_breakdown import _credit_card_cycle_month


router = APIRouter(
    prefix="/finance",
    tags=["finance"],
)


def _month_key(value) -> str:
    return f"{value.year}-{value.month:02d}"


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
    pix_sent_by_month: dict[str, float] = {}
    pix_received_by_month: dict[str, float] = {}

    for account in accounts:
        account_type = normalize_text(account.get("type"))

        for transaction in account.get("transactions") or []:
            if not isinstance(transaction, dict):
                continue

            amount = transaction_amount_abs(transaction)
            if amount <= 0:
                continue

            if account_type == "CREDIT" and is_credit_card_purchase(transaction):
                key = _credit_card_cycle_month(transaction)
                if key is not None:
                    card_by_month[key] = card_by_month.get(key, 0.0) + amount

            if account_type == "BANK" and is_pix_transaction(transaction):
                transaction_date = parse_transaction_date(transaction)
                if transaction_date is None:
                    continue

                key = _month_key(transaction_date)
                if is_outflow_transaction(transaction):
                    pix_sent_by_month[key] = (
                        pix_sent_by_month.get(key, 0.0) + amount
                    )
                else:
                    pix_received_by_month[key] = (
                        pix_received_by_month.get(key, 0.0) + amount
                    )

    return {
        "credit_card_commitments_by_month": {
            key: round(value, 2)
            for key, value in card_by_month.items()
        },
        "pix_sent_by_month": {
            key: round(value, 2)
            for key, value in pix_sent_by_month.items()
        },
        "pix_received_by_month": {
            key: round(value, 2)
            for key, value in pix_received_by_month.items()
        },
    }
