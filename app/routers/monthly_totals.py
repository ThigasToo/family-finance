from copy import deepcopy
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.card_schedule import build_card_schedule, filter_card_schedule
from app.database import get_db
from app.models import (
    FinancialSnapshot,
    MonthlyCardPeriod,
    MonthlyManualCommitment,
    User,
)
from app.security import get_current_user


router = APIRouter(prefix="/finance", tags=["finance"])


def _item_date(item: dict):
    raw = item.get("date")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _sum_items(items: list[dict]) -> float:
    return round(
        sum(float(item.get("amount") or 0) for item in items),
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
    schedule = build_card_schedule(accounts)

    card_by_month: dict[str, float] = {}
    for item in schedule:
        item_date = _item_date(item)
        if item_date is None:
            continue
        key = f"{item_date.year}-{item_date.month:02d}"
        card_by_month[key] = card_by_month.get(key, 0.0) + float(item.get("amount") or 0)

    period_rows = (
        db.query(MonthlyCardPeriod)
        .filter(MonthlyCardPeriod.user_id == current_user.id)
        .all()
    )

    card_periods_by_month = {}
    for row in period_rows:
        filtered = filter_card_schedule(accounts, row.date_from, row.date_to)
        card_by_month[row.month] = _sum_items(filtered)
        card_periods_by_month[row.month] = {
            "date_from": row.date_from.isoformat(),
            "date_to": row.date_to.isoformat(),
        }

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
        "card_periods_by_month": card_periods_by_month,
        "manual_commitments_by_month": manual_by_month,
        "pix_sent_by_month": manual_by_month,
    }
