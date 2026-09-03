from calendar import monthrange
from copy import deepcopy
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.cash_flow import build_monthly_cash_flow
from app.database import get_db
from app.investment_snapshot import ensure_investment_transactions
from app.models import FinancialSnapshot, MonthlyFinancialSnapshot, User
from app.security import get_current_user
from app.routers.finance import (
    is_credit_card_purchase,
    is_outflow_transaction,
    is_pix_transaction,
    normalize_text,
    parse_transaction_date,
    resolve_account_institution,
    transaction_amount_abs,
)


router = APIRouter(
    prefix="/finance",
    tags=["finance"],
)


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
    return (
        date(parsed.year, parsed.month, 1),
        date(parsed.year, parsed.month, last_day),
    )


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
    if parsed is None:
        return None
    return parsed.isoformat()


def _month_key(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def _extract_installment(transaction: dict) -> dict:
    metadata = transaction.get("creditCardMetadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    number = None
    total = None

    for key in (
        "installmentNumber",
        "installment_number",
        "currentInstallment",
        "current_installment",
    ):
        if metadata.get(key) is not None:
            number = metadata.get(key)
            break
        if transaction.get(key) is not None:
            number = transaction.get(key)
            break

    for key in (
        "totalInstallments",
        "total_installments",
        "installments",
        "installmentCount",
        "installment_count",
    ):
        if metadata.get(key) is not None:
            total = metadata.get(key)
            break
        if transaction.get(key) is not None:
            total = transaction.get(key)
            break

    return {
        "number": number,
        "total": total,
    }


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

            transaction_month = _month_key(
                transaction_date.year,
                transaction_date.month,
            )
            if transaction_month != month:
                continue

            amount = transaction_amount_abs(transaction)
            if amount <= 0:
                continue

            is_outflow = is_outflow_transaction(transaction)
            direction = "OUT" if is_outflow else "IN"

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
                    "signed_amount": round(
                        -amount if is_outflow else amount,
                        2,
                    ),
                    "direction": direction,
                    "date": _transaction_date_iso(transaction),
                    "category": transaction.get("category"),
                    "counterparty": counterparty,
                }
            )

    items.sort(
        key=lambda item: item.get("date") or "",
        reverse=True,
    )
    return items


def build_credit_card_breakdown(
    accounts: list,
    date_from: date,
    date_to: date,
) -> list[dict]:
    items: list[dict] = []

    for account in accounts:
        if normalize_text(account.get("type")) != "CREDIT":
            continue

        institution = resolve_account_institution(
            account,
            fallback=account.get("institution_name"),
        )

        for transaction in account.get("transactions") or []:
            if not isinstance(transaction, dict):
                continue
            if not is_credit_card_purchase(transaction):
                continue

            transaction_date = parse_transaction_date(transaction)
            if transaction_date is None:
                continue

            transaction_day = transaction_date.date()
            if transaction_day < date_from or transaction_day > date_to:
                continue

            amount = transaction_amount_abs(transaction)
            if amount <= 0:
                continue

            metadata = transaction.get("creditCardMetadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}

            installment = _extract_installment(transaction)

            items.append(
                {
                    "id": transaction.get("id"),
                    "institution": institution,
                    "card_id": account.get("id"),
                    "card_name": _account_display_name(account),
                    "description": _transaction_description(transaction),
                    "amount": round(amount, 2),
                    "date": transaction_date.isoformat(),
                    "transaction_month": _month_key(
                        transaction_date.year,
                        transaction_date.month,
                    ),
                    "bill_forecast_date": metadata.get("billForecastDate"),
                    "bill_date": metadata.get("billDate"),
                    "due_date": metadata.get("dueDate"),
                    "installment_number": installment["number"],
                    "installment_total": installment["total"],
                }
            )

    items.sort(
        key=lambda item: item.get("date") or "",
        reverse=True,
    )
    return items


def build_monthly_breakdown_payload(
    accounts: list,
    investments: list,
    month: str,
    card_date_from: date,
    card_date_to: date,
    source_updated_at: datetime | None = None,
) -> dict:
    """Monta a resposta mensal usando as mesmas regras atuais do endpoint."""

    raw_pix_items = build_pix_breakdown(accounts, month)
    card_items = build_credit_card_breakdown(
        accounts,
        card_date_from,
        card_date_to,
    )
    cash_flow = build_monthly_cash_flow(
        accounts,
        investments,
        month,
    )

    raw_pix_sent_total = round(
        sum(
            float(item["amount"])
            for item in raw_pix_items
            if item.get("direction") == "OUT"
        ),
        2,
    )
    raw_pix_received_total = round(
        sum(
            float(item["amount"])
            for item in raw_pix_items
            if item.get("direction") == "IN"
        ),
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

    card_total = round(
        sum(float(item["amount"]) for item in card_items),
        2,
    )

    return {
        "month": month,
        "credit_cards": {
            "total": card_total,
            "count": len(card_items),
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
        "updated_at": (
            source_updated_at.isoformat()
            if source_updated_at
            else None
        ),
    }


def persist_monthly_financial_snapshot(
    db: Session,
    user_id: int,
    month: str,
    payload: dict,
    source_updated_at: datetime | None,
) -> bool:
    """Salva o snapshot mensal sem impedir a resposta em caso de falha."""

    try:
        monthly_snapshot = (
            db.query(MonthlyFinancialSnapshot)
            .filter(
                MonthlyFinancialSnapshot.user_id == user_id,
                MonthlyFinancialSnapshot.month == month,
            )
            .first()
        )

        if monthly_snapshot is None:
            monthly_snapshot = MonthlyFinancialSnapshot(
                user_id=user_id,
                month=month,
                payload=deepcopy(payload),
                source_updated_at=source_updated_at,
            )
            db.add(monthly_snapshot)
        else:
            monthly_snapshot.payload = deepcopy(payload)
            monthly_snapshot.source_updated_at = source_updated_at

        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        print(
            "Erro ao persistir snapshot financeiro mensal "
            f"do usuário {user_id} em {month}: {exc}"
        )
        return False


def _normalized_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _monthly_snapshot_matches_source(
    monthly_snapshot: MonthlyFinancialSnapshot,
    financial_snapshot: FinancialSnapshot | None,
) -> bool:
    monthly_source = _normalized_timestamp(monthly_snapshot.source_updated_at)
    financial_source = _normalized_timestamp(
        financial_snapshot.updated_at if financial_snapshot else None
    )
    return monthly_source == financial_source


def _monthly_snapshot_matches_card_period(
    payload: dict,
    card_date_from: date,
    card_date_to: date,
) -> bool:
    credit_cards = payload.get("credit_cards")
    if not isinstance(credit_cards, dict):
        return False

    return (
        credit_cards.get("date_from") == card_date_from.isoformat()
        and credit_cards.get("date_to") == card_date_to.isoformat()
    )


def get_valid_monthly_snapshot_payload(
    db: Session,
    user_id: int,
    month: str,
    financial_snapshot: FinancialSnapshot | None,
    card_date_from: date,
    card_date_to: date,
) -> dict | None:
    """Retorna o snapshot somente quando fonte e período ainda são válidos."""

    monthly_snapshot = (
        db.query(MonthlyFinancialSnapshot)
        .filter(
            MonthlyFinancialSnapshot.user_id == user_id,
            MonthlyFinancialSnapshot.month == month,
        )
        .first()
    )
    if monthly_snapshot is None:
        return None

    payload = monthly_snapshot.payload or {}
    if not isinstance(payload, dict):
        return None
    if payload.get("month") != month:
        return None
    if not _monthly_snapshot_matches_source(
        monthly_snapshot,
        financial_snapshot,
    ):
        return None
    if not _monthly_snapshot_matches_card_period(
        payload,
        card_date_from,
        card_date_to,
    ):
        return None

    return deepcopy(payload)


@router.get("/monthly-breakdown")
async def get_monthly_breakdown(
    month: str = Query(
        ...,
        description="Mês de referência no formato YYYY-MM",
        examples=["2026-09"],
    ),
    date_from: str | None = Query(
        None,
        description="Data inicial opcional dos cartões no formato YYYY-MM-DD",
    ),
    date_to: str | None = Query(
        None,
        description="Data final opcional dos cartões no formato YYYY-MM-DD",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month = _validate_month(month)
    card_date_from, card_date_to = _resolve_card_date_range(
        month,
        date_from,
        date_to,
    )

    snapshot = (
        db.query(FinancialSnapshot)
        .filter(FinancialSnapshot.user_id == current_user.id)
        .first()
    )

    cached_payload = get_valid_monthly_snapshot_payload(
        db=db,
        user_id=current_user.id,
        month=month,
        financial_snapshot=snapshot,
        card_date_from=card_date_from,
        card_date_to=card_date_to,
    )
    if cached_payload is not None:
        return cached_payload

    payload = deepcopy(snapshot.payload or {}) if snapshot else {}
    accounts = payload.get("accounts") or []
    investments = payload.get("investments") or []

    changed = await ensure_investment_transactions(investments)
    if changed and snapshot is not None:
        payload["investments"] = investments
        snapshot.payload = payload
        db.commit()

    response_payload = build_monthly_breakdown_payload(
        accounts=accounts,
        investments=investments,
        month=month,
        card_date_from=card_date_from,
        card_date_to=card_date_to,
        source_updated_at=(snapshot.updated_at if snapshot else None),
    )

    persist_monthly_financial_snapshot(
        db=db,
        user_id=current_user.id,
        month=month,
        payload=response_payload,
        source_updated_at=(snapshot.updated_at if snapshot else None),
    )

    return response_payload
