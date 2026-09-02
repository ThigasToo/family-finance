from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
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


class PluggyWebhookIn(BaseModel):
    event: str
    eventId: str | None = None
    itemId: str | None = None
    accountId: str | None = None
    transactionIds: list[str] | None = None
    clientUserId: str | None = None


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


@router.post("/webhook")
async def receive_pluggy_webhook(
    payload: PluggyWebhookIn,
    x_family_finance_webhook_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Atualiza o snapshot quando a Pluggy informa mudanças relevantes.

    O endpoint fica desabilitado até `PLUGGY_WEBHOOK_SECRET` ser configurado
    no ambiente e o mesmo valor ser enviado pela Pluggy como header customizado.
    """
    expected_secret = settings.pluggy_webhook_secret.strip()
    if not expected_secret:
        raise HTTPException(
            status_code=503,
            detail="Webhook Pluggy ainda não configurado",
        )

    if x_family_finance_webhook_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Webhook não autorizado")

    event = payload.event.strip().lower()
    relevant_events = {
        "item/created",
        "item/updated",
        "transactions/created",
        "transactions/updated",
        "transactions/deleted",
    }
    if event not in relevant_events:
        return {"status": "ignored", "event": payload.event}

    if not payload.itemId:
        return {"status": "ignored", "reason": "missing itemId"}

    item = (
        db.query(PluggyItem)
        .filter(PluggyItem.item_id == payload.itemId)
        .first()
    )
    if item is None:
        return {"status": "ignored", "reason": "unknown item"}

    sync_result = await sync_pluggy_item_snapshot(
        db,
        item.user_id,
        item,
    )

    return {
        "status": "ok",
        "event": payload.event,
        "sync_status": "ok" if sync_result["complete"] else "partial",
    }
