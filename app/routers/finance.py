from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, PluggyItem, FinancialSnapshot
from app.security import get_current_user
from app.schemas import FinanceSummaryOut, FinanceRefreshOut
from app.pluggy_client import fetch_accounts, fetch_transactions, fetch_investments

router = APIRouter(prefix="/finance", tags=["finance"])

COOLDOWN_MINUTES = 5


@router.get("/summary", response_model=FinanceSummaryOut)
def get_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    snapshot = db.query(FinancialSnapshot).filter(FinancialSnapshot.user_id == current_user.id).first()
    if not snapshot:
        return FinanceSummaryOut(payload={"accounts": [], "investments": []}, updated_at=None)
    return FinanceSummaryOut(payload=snapshot.payload, updated_at=snapshot.updated_at)


@router.post("/refresh", response_model=FinanceRefreshOut)
async def refresh_finance(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    snapshot = db.query(FinancialSnapshot).filter(FinancialSnapshot.user_id == current_user.id).first()

    if snapshot and snapshot.updated_at:
        elapsed = datetime.now(timezone.utc) - snapshot.updated_at.replace(tzinfo=timezone.utc)
        if elapsed < timedelta(minutes=COOLDOWN_MINUTES):
            wait_seconds = int((timedelta(minutes=COOLDOWN_MINUTES) - elapsed).total_seconds())
            raise HTTPException(
                status_code=429,
                detail=f"Aguarde {wait_seconds}s antes de atualizar novamente",
            )

    items = db.query(PluggyItem).filter(PluggyItem.user_id == current_user.id).all()

    all_accounts = []
    all_investments = []

    for item in items:
        accounts = await fetch_accounts(item.item_id)
        for account in accounts:
            if account.get("type") in ("BANK", "CREDIT"):
                try:
                    transactions = await fetch_transactions(account["id"])
                except Exception:
                    transactions = []
                account["transactions"] = transactions
            else:
                account["transactions"] = []
        all_accounts.extend(accounts)

        investments = await fetch_investments(item.item_id)
        all_investments.extend(investments)

    payload = {"accounts": all_accounts, "investments": all_investments}
    now = datetime.now(timezone.utc)

    if snapshot:
        snapshot.payload = payload
        snapshot.updated_at = now
    else:
        snapshot = FinancialSnapshot(user_id=current_user.id, payload=payload, updated_at=now)
        db.add(snapshot)

    db.commit()

    return FinanceRefreshOut(status="ok", updated_at=now)