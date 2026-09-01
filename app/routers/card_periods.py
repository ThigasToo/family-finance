from calendar import monthrange
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MonthlyCardPeriod, User
from app.security import get_current_user


router = APIRouter(prefix="/finance", tags=["finance"])


class CardPeriodIn(BaseModel):
    date_from: date
    date_to: date


def _validate_month(month: str) -> str:
    try:
        parsed = datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="O parâmetro month deve estar no formato YYYY-MM",
        ) from exc
    return f"{parsed.year}-{parsed.month:02d}"


def _default_period(month: str) -> tuple[date, date]:
    parsed = datetime.strptime(month, "%Y-%m")
    last_day = monthrange(parsed.year, parsed.month)[1]
    return date(parsed.year, parsed.month, 1), date(parsed.year, parsed.month, last_day)


def _response(month: str, row: MonthlyCardPeriod | None) -> dict:
    if row is None:
        date_from, date_to = _default_period(month)
        return {
            "month": month,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "custom": False,
            "updated_at": None,
        }

    return {
        "month": month,
        "date_from": row.date_from.isoformat(),
        "date_to": row.date_to.isoformat(),
        "custom": True,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/card-period")
def get_card_period(
    month: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month = _validate_month(month)
    row = (
        db.query(MonthlyCardPeriod)
        .filter(
            MonthlyCardPeriod.user_id == current_user.id,
            MonthlyCardPeriod.month == month,
        )
        .first()
    )
    return _response(month, row)


@router.put("/card-period")
def save_card_period(
    payload: CardPeriodIn,
    month: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month = _validate_month(month)
    if payload.date_from > payload.date_to:
        raise HTTPException(
            status_code=422,
            detail="date_from não pode ser posterior a date_to",
        )

    row = (
        db.query(MonthlyCardPeriod)
        .filter(
            MonthlyCardPeriod.user_id == current_user.id,
            MonthlyCardPeriod.month == month,
        )
        .first()
    )

    if row is None:
        row = MonthlyCardPeriod(
            user_id=current_user.id,
            month=month,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
        db.add(row)
    else:
        row.date_from = payload.date_from
        row.date_to = payload.date_to

    db.commit()
    db.refresh(row)
    return _response(month, row)


@router.delete("/card-period")
def reset_card_period(
    month: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month = _validate_month(month)
    row = (
        db.query(MonthlyCardPeriod)
        .filter(
            MonthlyCardPeriod.user_id == current_user.id,
            MonthlyCardPeriod.month == month,
        )
        .first()
    )
    if row is not None:
        db.delete(row)
        db.commit()
    return _response(month, None)
