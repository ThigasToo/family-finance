from copy import deepcopy
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FinancialSnapshot, PluggyItem, User
from app.pluggy_client import fetch_accounts, fetch_investments, fetch_transactions
from app.schemas import FinanceRefreshOut, FinanceSummaryOut
from app.security import get_current_user
from app.routers.finance import (
    enrich_transaction,
    get_summary as legacy_get_summary,
    is_active_pluggy_investment,
    normalize_institution_name,
    normalize_text,
    resolve_account_institution,
    resolve_investment_institution,
)


router = APIRouter(prefix="/finance", tags=["finance"])
COOLDOWN_MINUTES = 5
_ITEM_KEY = "_pluggy_item_id"


def _record_institution(record: dict) -> str | None:
    for key in (
        "resolved_institution",
        "institution_name",
        "institutionName",
    ):
        normalized = normalize_institution_name(record.get(key))
        if normalized:
            return normalized

    institution = record.get("institution")
    if isinstance(institution, dict):
        return normalize_institution_name(institution.get("name"))
    if isinstance(institution, str):
        return normalize_institution_name(institution)
    return None


def _belongs_to_item(record: dict, item: PluggyItem) -> bool:
    tagged_item = record.get(_ITEM_KEY)
    if tagged_item:
        return str(tagged_item) == str(item.item_id)

    # Compatibilidade com snapshots antigos, anteriores à marcação por item.
    expected = normalize_institution_name(item.institution_name)
    actual = _record_institution(record)
    return bool(expected and actual and expected == actual)


def _previous_for_item(records: list, item: PluggyItem) -> list[dict]:
    return [
        deepcopy(record)
        for record in records
        if isinstance(record, dict) and _belongs_to_item(record, item)
    ]


def _previous_account_by_id(records: list) -> dict[str, dict]:
    return {
        str(record.get("id")): record
        for record in records
        if isinstance(record, dict) and record.get("id")
    }


async def _load_accounts_for_item(
    item: PluggyItem,
    previous_accounts: list,
    now: datetime,
) -> tuple[list[dict], bool]:
    previous_item_accounts = _previous_for_item(previous_accounts, item)
    previous_by_id = _previous_account_by_id(previous_accounts)

    try:
        accounts = await fetch_accounts(item.item_id)
    except Exception:
        return previous_item_accounts, False

    prepared: list[dict] = []
    transactions_complete = True

    for raw_account in accounts:
        if not isinstance(raw_account, dict):
            continue

        account = deepcopy(raw_account)
        institution_name = resolve_account_institution(
            account,
            fallback=item.institution_name,
        )
        account["institution_name"] = institution_name
        account["resolved_institution"] = institution_name
        account["source"] = "PLUGGY"
        account[_ITEM_KEY] = item.item_id

        account_type = normalize_text(account.get("type"))
        if account_type not in {"BANK", "CREDIT"}:
            account["transactions"] = []
            prepared.append(account)
            continue

        try:
            if account_type == "CREDIT":
                transactions = await fetch_transactions(
                    str(account["id"]),
                    date_from=now - timedelta(days=365),
                    date_to=now + timedelta(days=365),
                )
            else:
                transactions = await fetch_transactions(
                    str(account["id"]),
                    date_from=now - timedelta(days=365),
                    date_to=now,
                )

            account["transactions"] = [
                enrich_transaction(transaction)
                for transaction in transactions
                if isinstance(transaction, dict)
            ]
        except Exception:
            transactions_complete = False
            previous = previous_by_id.get(str(account.get("id")), {})
            account["transactions"] = deepcopy(
                previous.get("transactions") or []
            )

        prepared.append(account)

    return prepared, transactions_complete


async def _load_investments_for_item(
    item: PluggyItem,
    previous_investments: list,
) -> tuple[list[dict], bool]:
    previous_item_investments = _previous_for_item(
        previous_investments,
        item,
    )

    try:
        raw_investments = await fetch_investments(item.item_id)
    except Exception:
        return previous_item_investments, False

    prepared: list[dict] = []
    for raw_investment in raw_investments:
        if not isinstance(raw_investment, dict):
            continue
        if not is_active_pluggy_investment(raw_investment):
            continue

        investment = deepcopy(raw_investment)
        institution_name = resolve_investment_institution(
            investment,
            fallback=item.institution_name,
        )
        investment["institution_name"] = institution_name
        investment["resolved_institution"] = institution_name
        investment["source"] = "PLUGGY"
        investment[_ITEM_KEY] = item.item_id
        prepared.append(investment)

    return prepared, True


async def _load_item_data(
    item: PluggyItem,
    previous_payload: dict,
    now: datetime,
) -> tuple[list[dict], list[dict], bool]:
    accounts, accounts_complete = await _load_accounts_for_item(
        item,
        previous_payload.get("accounts") or [],
        now,
    )
    investments, investments_complete = await _load_investments_for_item(
        item,
        previous_payload.get("investments") or [],
    )
    return accounts, investments, accounts_complete and investments_complete


async def sync_pluggy_item_snapshot(
    db: Session,
    user_id: int,
    item: PluggyItem,
) -> dict:
    """Sincroniza somente o item recém-conectado, sem aplicar cooldown."""

    snapshot = (
        db.query(FinancialSnapshot)
        .filter(FinancialSnapshot.user_id == user_id)
        .first()
    )
    previous_payload = deepcopy(snapshot.payload or {}) if snapshot else {}
    previous_accounts = previous_payload.get("accounts") or []
    previous_investments = previous_payload.get("investments") or []
    now = datetime.now(timezone.utc)

    accounts, investments, complete = await _load_item_data(
        item,
        previous_payload,
        now,
    )

    kept_accounts = [
        deepcopy(record)
        for record in previous_accounts
        if not (isinstance(record, dict) and _belongs_to_item(record, item))
    ]
    kept_investments = [
        deepcopy(record)
        for record in previous_investments
        if not (isinstance(record, dict) and _belongs_to_item(record, item))
    ]

    payload = {
        "accounts": kept_accounts + accounts,
        "investments": kept_investments + investments,
    }

    if snapshot is None:
        # Se a Pluggy estiver parcialmente indisponível, não bloqueamos uma
        # tentativa manual de refresh logo após a conexão.
        snapshot_time = (
            now
            if complete
            else now - timedelta(minutes=COOLDOWN_MINUTES)
        )
        snapshot = FinancialSnapshot(
            user_id=user_id,
            payload=payload,
            updated_at=snapshot_time,
        )
        db.add(snapshot)
    else:
        snapshot.payload = payload
        if complete:
            snapshot.updated_at = now

    db.commit()
    return {
        "complete": complete,
        "accounts": len(accounts),
        "investments": len(investments),
    }


@router.get("/summary", response_model=FinanceSummaryOut)
def get_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return legacy_get_summary(current_user=current_user, db=db)


@router.post("/refresh", response_model=FinanceRefreshOut)
async def refresh_finance(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    snapshot = (
        db.query(FinancialSnapshot)
        .filter(FinancialSnapshot.user_id == current_user.id)
        .first()
    )

    if snapshot and snapshot.updated_at:
        updated_at = snapshot.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)

        elapsed = datetime.now(timezone.utc) - updated_at
        if elapsed < timedelta(minutes=COOLDOWN_MINUTES):
            wait_seconds = int(
                (timedelta(minutes=COOLDOWN_MINUTES) - elapsed).total_seconds()
            )
            raise HTTPException(
                status_code=429,
                detail=f"Aguarde {wait_seconds}s antes de atualizar novamente",
            )

    items = (
        db.query(PluggyItem)
        .filter(PluggyItem.user_id == current_user.id)
        .all()
    )
    previous_payload = deepcopy(snapshot.payload or {}) if snapshot else {}
    now = datetime.now(timezone.utc)

    all_accounts: list[dict] = []
    all_investments: list[dict] = []
    complete = True

    for item in items:
        accounts, investments, item_complete = await _load_item_data(
            item,
            previous_payload,
            now,
        )
        all_accounts.extend(accounts)
        all_investments.extend(investments)
        complete = complete and item_complete

    payload = {
        "accounts": all_accounts,
        "investments": all_investments,
    }

    if snapshot is None:
        snapshot = FinancialSnapshot(
            user_id=current_user.id,
            payload=payload,
            updated_at=(
                now
                if complete
                else now - timedelta(minutes=COOLDOWN_MINUTES)
            ),
        )
        db.add(snapshot)
    else:
        snapshot.payload = payload
        if complete:
            snapshot.updated_at = now

    db.commit()

    return FinanceRefreshOut(status="ok", updated_at=now)
