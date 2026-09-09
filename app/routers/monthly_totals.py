from copy import deepcopy

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    FinancialSnapshot,
    MonthlyCardPeriod,
    MonthlyManualCardEntry,
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


router = APIRouter(prefix="/finance", tags=["finance"])


def _card_transactions(accounts: list) -> list[tuple]:
    transactions: list[tuple] = []

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

            transactions.append((transaction_date.date(), amount))

    return transactions


def _sum_period(transactions: list[tuple], date_from, date_to) -> float:
    return round(
        sum(
            amount
            for transaction_date, amount in transactions
            if date_from <= transaction_date <= date_to
        ),
        2,
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
    transactions = _card_transactions(accounts)

    card_by_month: dict[str, float] = {}
    for transaction_date, amount in transactions:
        key = f"{transaction_date.year}-{transaction_date.month:02d}"
        card_by_month[key] = card_by_month.get(key, 0.0) + amount

    period_rows = (
        db.query(MonthlyCardPeriod)
        .filter(MonthlyCardPeriod.user_id == current_user.id)
        .all()
    )

    card_periods_by_month = {}
    for row in period_rows:
        card_by_month[row.month] = _sum_period(
            transactions,
            row.date_from,
            row.date_to,
        )
        card_periods_by_month[row.month] = {
            "date_from": row.date_from.isoformat(),
            "date_to": row.date_to.isoformat(),
        }

    manual_card_rows = (
        db.query(MonthlyManualCardEntry)
        .filter(MonthlyManualCardEntry.user_id == current_user.id)
        .all()
    )
    manual_card_by_month: dict[str, float] = {}
    for row in manual_card_rows:
        manual_card_by_month[row.month] = (
            manual_card_by_month.get(row.month, 0.0) + float(row.amount)
        )

    for month, amount in manual_card_by_month.items():
        card_by_month[month] = card_by_month.get(month, 0.0) + amount

    manual_rows = (
        db.query(MonthlyManualCommitment)
        .filter(MonthlyManualCommitment.user_id == current_user.id)
        .all()
    )

    manual_by_month = {
        row.month: round(float(row.amount), 2)
        for row in manual_rows
    }

    return {
        "credit_card_commitments_by_month": {
            key: round(value, 2)
            for key, value in card_by_month.items()
        },
        "manual_card_commitments_by_month": {
            key: round(value, 2)
            for key, value in manual_card_by_month.items()
        },
        "card_periods_by_month": card_periods_by_month,
        "manual_commitments_by_month": manual_by_month,
        "pix_sent_by_month": manual_by_month,
    }
