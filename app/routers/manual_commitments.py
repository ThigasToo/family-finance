from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MonthlyManualCommitment, User
from app.monthly_snapshot_cache import invalidate_monthly_snapshot
from app.security import get_current_user


router = APIRouter(
    prefix="/finance",
    tags=["finance"],
)


class ManualCommitmentIn(BaseModel):
    amount: float = Field(ge=0)


def _validate_month(month: str) -> str:
    try:
        parsed = datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="O parâmetro month deve estar no formato YYYY-MM",
        ) from exc

    return f"{parsed.year}-{parsed.month:02d}"


@router.get("/manual-commitment")
def get_manual_commitment(
    month: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month = _validate_month(month)

    row = (
        db.query(MonthlyManualCommitment)
        .filter(
            MonthlyManualCommitment.user_id == current_user.id,
            MonthlyManualCommitment.month == month,
        )
        .first()
    )

    return {
        "month": month,
        "amount": round(float(row.amount), 2) if row else 0.0,
        "updated_at": row.updated_at.isoformat() if row else None,
    }


@router.put("/manual-commitment")
def save_manual_commitment(
    data: ManualCommitmentIn,
    month: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month = _validate_month(month)

    row = (
        db.query(MonthlyManualCommitment)
        .filter(
            MonthlyManualCommitment.user_id == current_user.id,
            MonthlyManualCommitment.month == month,
        )
        .first()
    )

    if row is None:
        row = MonthlyManualCommitment(
            user_id=current_user.id,
            month=month,
            amount=data.amount,
        )
        db.add(row)
    else:
        row.amount = data.amount

    invalidate_monthly_snapshot(db, current_user.id, month)
    db.commit()
    db.refresh(row)

    return {
        "month": month,
        "amount": round(float(row.amount), 2),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
