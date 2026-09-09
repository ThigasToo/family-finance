from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MonthlyManualCardEntry, User
from app.monthly_snapshot_cache import invalidate_monthly_snapshot
from app.security import get_current_user


router = APIRouter(prefix="/finance", tags=["finance"])


class ManualCardEntryIn(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    amount: float = Field(gt=0)
    institution: str | None = Field(default=None, max_length=255)


def _validate_month(month: str) -> str:
    try:
        parsed = datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="O parâmetro month deve estar no formato YYYY-MM",
        ) from exc
    return f"{parsed.year}-{parsed.month:02d}"


def _serialize(row: MonthlyManualCardEntry) -> dict:
    return {
        "id": row.id,
        "month": row.month,
        "description": row.description,
        "institution": row.institution,
        "amount": round(float(row.amount), 2),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/manual-card-entries")
def list_manual_card_entries(
    month: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month = _validate_month(month)
    rows = (
        db.query(MonthlyManualCardEntry)
        .filter(
            MonthlyManualCardEntry.user_id == current_user.id,
            MonthlyManualCardEntry.month == month,
        )
        .order_by(MonthlyManualCardEntry.created_at.desc())
        .all()
    )
    return {
        "month": month,
        "total": round(sum(float(row.amount) for row in rows), 2),
        "count": len(rows),
        "items": [_serialize(row) for row in rows],
    }


@router.post("/manual-card-entries", status_code=status.HTTP_201_CREATED)
def create_manual_card_entry(
    data: ManualCardEntryIn,
    month: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month = _validate_month(month)
    row = MonthlyManualCardEntry(
        user_id=current_user.id,
        month=month,
        description=data.description.strip(),
        institution=(data.institution or "").strip() or None,
        amount=data.amount,
    )
    db.add(row)
    invalidate_monthly_snapshot(db, current_user.id, month)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.put("/manual-card-entries/{entry_id}")
def update_manual_card_entry(
    entry_id: int,
    data: ManualCardEntryIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(MonthlyManualCardEntry)
        .filter(
            MonthlyManualCardEntry.id == entry_id,
            MonthlyManualCardEntry.user_id == current_user.id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Ajuste manual não encontrado")

    row.description = data.description.strip()
    row.institution = (data.institution or "").strip() or None
    row.amount = data.amount
    invalidate_monthly_snapshot(db, current_user.id, row.month)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.delete("/manual-card-entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_manual_card_entry(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(MonthlyManualCardEntry)
        .filter(
            MonthlyManualCardEntry.id == entry_id,
            MonthlyManualCardEntry.user_id == current_user.id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Ajuste manual não encontrado")

    month = row.month
    db.delete(row)
    invalidate_monthly_snapshot(db, current_user.id, month)
    db.commit()
    return None
