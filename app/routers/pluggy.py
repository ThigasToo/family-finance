from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PluggyItem, User
from app.pluggy_client import create_connect_token, fetch_item
from app.security import get_current_user
from app.routers.finance_stable import sync_pluggy_item_snapshot


router = APIRouter(prefix="/pluggy", tags=["pluggy"])


class ConnectTokenOut(BaseModel):
    connect_token: str


class RegisterItemIn(BaseModel):
    item_id: str


@router.post("/connect-token", response_model=ConnectTokenOut)
async def get_connect_token(
    current_user: User = Depends(get_current_user),
):
    token = await create_connect_token(
        client_user_id=str(current_user.id)
    )
    return ConnectTokenOut(connect_token=token)


@router.post("/items")
async def register_item(
    payload: RegisterItemIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(PluggyItem)
        .filter(PluggyItem.item_id == payload.item_id)
        .first()
    )
    if existing:
        if existing.user_id == current_user.id:
            sync_result = await sync_pluggy_item_snapshot(
                db,
                current_user.id,
                existing,
            )
            return {
                "status": "ok",
                "institution_name": existing.institution_name,
                "sync_status": (
                    "ok" if sync_result["complete"] else "partial"
                ),
            }

        raise HTTPException(
            status_code=400,
            detail="Esse item já está registrado",
        )

    item_data = await fetch_item(payload.item_id)
    institution_name = item_data.get("connector", {}).get("name")

    item = PluggyItem(
        user_id=current_user.id,
        item_id=payload.item_id,
        institution_name=institution_name,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    sync_result = await sync_pluggy_item_snapshot(
        db,
        current_user.id,
        item,
    )

    return {
        "status": "ok",
        "institution_name": institution_name,
        "sync_status": (
            "ok" if sync_result["complete"] else "partial"
        ),
        "accounts_synced": sync_result["accounts"],
        "investments_synced": sync_result["investments"],
    }
