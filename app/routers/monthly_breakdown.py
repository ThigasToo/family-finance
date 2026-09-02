from calendar import monthrange
from copy import deepcopy
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.card_schedule import filter_card_schedule
from app.cash_flow import build_monthly_cash_flow
from app.database import get_db
from app.investment_snapshot import ensure_investment_transactions
from app.models import FinancialSnapshot, User
from app.security import get_current_user
from app.routers.finance import (
    is_outflow_transaction,
    is_pix_transaction,
    normalize_text,
    parse_transaction_date,
    resolve_account_institution,
    transaction_amount_abs,
)


router = APIRouter(prefix="/finance", tags=["finance"])


def _validate_month(month: str) -> str:
    try:
        parsed = datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="O parâmetro month deve estar no formato YYYY-MM",
        ) from exc
    return f"{parsed.year}-{parsed.month:02d}"


def _month_date_range(month: str) -> tuple[date, date]:
    parsed = datetime.strptime(month, "%Y-%m")
    last_day = monthrange(parsed.year, parsed.month)[1]
    return date(parsed.year, parsed.month, 1), date(parsed.year, parsed.month, last_day)


def _parse_filter_date(value: str | None, field: str) -> date | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"O parâmetro {field} deve estar no formato YYYY-MM-DD",
        ) from exc


def _resolve_card_date_range(
    month: str,
    date_from: str | None,
    date_to: str | None,
) -> tuple[date, date]:
    default_from, default_to = _month_date_range(month)
    resolved_from = _parse_filter_date(date_from, "date_from") or default_from
    resolved_to = _parse_filter_date(date_to, "date_to") or default_to
    if resolved_from > resolved_to:
        raise HTTPException(
            status_code=422,
            detail="date_from não pode ser posterior a date_to",
        )
    return resolved_from, resolved_to


def _first_non_empty(*values):
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _account_display_name(account: dict) -> str:
    return (
        _first_non_empty(
            account.get("name"),
            account.get("marketingName"),
            account.get("number"),
        )
        or "Conta"
    )


def _transaction_description(transaction: dict) -> str:
    return (
        _first_non_empty(
            transaction.get("description"),
            transaction.get("descriptionRaw"),
            transaction.get("merchant"),
        )
        or "Lançamento"
    )


def _transaction_date_iso(transaction: dict) -> str | None:
    parsed = parse_transaction_date(transaction)
    return parsed.isoformat() if parsed is not None else None


def _month_key(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def build_pix_breakdown(accounts: list, month: str) -> list[dict]:
    items: list[dict] = []

    for account in accounts:
        if normalize_text(account.get("type")) != "BANK":
            continue

        institution = resolve_account_institution(
            account,
            fallback=account.get("institution_name"),
        )

        for transaction in account.get("transactions") or []:
            if not isinstance(transaction, dict):
                continue
            if not is_pix_transaction(transaction):
                continue

            transaction_date = parse_transaction_date(transaction)
            if transaction_date is None:
                continue

            transaction_month = _month_key(transaction_date.year, transaction_date.month)
            if transaction_month != month:
                continue

            amount = transaction_amount_abs(transaction)
            if amount <= 0:
                continue

            is_outflow = is_outflow_transaction(transaction)
            payment_data = transaction.get("paymentData") or {}
            if not isinstance(payment_data, dict):
                payment_data = {}

            counterparty = _first_non_empty(
                payment_data.get("receiverName") if is_outflow else None,
                payment_data.get("payerName") if not is_outflow else None,
                payment_data.get("receiverName"),
                payment_data.get("payerName"),
                transaction.get("counterpartyName"),
            )

            items.append(
                {
                    "id": transaction.get("id"),
                    "institution": institution,
                    "account_id": account.get("id"),
                    "account_name": _account_display_name(account),
                    "description": _transaction_description(transaction),
                    "amount": round(amount, 2),
                    "signed_amount": round(-amount if is_outflow else amount, 2),
                    "direction": "OUT" if is_outflow else "IN",
                    "date": _transaction_date_iso(transaction),
                    "category": transaction.get("category"),
                    "counterparty": counterparty,
                }
            )

    items.sort(key=lambda item: item.get("date") or "", reverse=True)
    return items


@router.get("/monthly-breakdown")
async def get_monthly_breakdown(
    month: str = Query(...),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month = _validate_month(month)
    card_date_from, card_date_to = _resolve_card_date_range(month, date_from, date_to)

    snapshot = (
        db.query(FinancialSnapshot)
        .filter(FinancialSnapshot.user_id == current_user.id)
        .first()
    )

    payload = deepcopy(snapshot.payload or {}) if snapshot else {}
    accounts = payload.get("accounts") or []
    investments = payload.get("investments") or []

    changed = await ensure_investment_transactions(investments)
    if changed and snapshot is not None:
        payload["investments"] = investments
        snapshot.payload = payload
        db.commit()

    raw_pix_items = build_pix_breakdown(accounts, month)
    card_items = filter_card_schedule(accounts, card_date_from, card_date_to)
    cash_flow = build_monthly_cash_flow(accounts, investments, month)

    raw_pix_sent_total = round(
        sum(float(item["amount"]) for item in raw_pix_items if item.get("direction") == "OUT"),
        2,
    )
    raw_pix_received_total = round(
        sum(float(item["amount"]) for item in raw_pix_items if item.get("direction") == "IN"),
        2,
    )
    cash_received = round(
        cash_flow["external_in"] + cash_flow["investment_redemptions"],
        2,
    )
    cash_sent = round(
        cash_flow["external_out"] + cash_flow["investment_applications"],
        2,
    )
    card_total = round(sum(float(item["amount"]) for item in card_items), 2)
    projected_total = round(
        sum(float(item["amount"]) for item in card_items if item.get("projected")),
        2,
    )

    return {
        "month": month,
        "credit_cards": {
            "total": card_total,
            "count": len(card_items),
            "projected_total": projected_total,
            "projected_count": sum(1 for item in card_items if item.get("projected")),
            "date_from": card_date_from.isoformat(),
            "date_to": card_date_to.isoformat(),
            "items": card_items,
        },
        "pix": {
            "total": cash_sent,
            "sent_total": cash_sent,
            "received_total": cash_received,
            "net": cash_flow["net"],
            "count": cash_flow["count"],
            "items": cash_flow["items"],
        },
        "raw_pix": {
            "sent_total": raw_pix_sent_total,
            "received_total": raw_pix_received_total,
            "net": round(raw_pix_received_total - raw_pix_sent_total, 2),
            "count": len(raw_pix_items),
            "items": raw_pix_items,
        },
        "cash_flow": cash_flow,
        "available_impact": round(cash_flow["net"] - card_total, 2),
        "updated_at": snapshot.updated_at.isoformat() if snapshot and snapshot.updated_at else None,
    }
