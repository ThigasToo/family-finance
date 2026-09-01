from copy import deepcopy
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FinancialSnapshot, User
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

BILLING_CYCLE_DAY = 5


def _validate_month(month: str) -> str:
    try:
        parsed = datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="O parâmetro month deve estar no formato YYYY-MM",
        ) from exc

    return f"{parsed.year}-{parsed.month:02d}"


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


def _previous_month(value: datetime) -> tuple[int, int]:
    if value.month == 1:
        return value.year - 1, 12
    return value.year, value.month - 1


def _credit_card_cycle_month(transaction: dict) -> str | None:
    """Classifica a compra pelo ciclo fixo de fechamento no dia 5.

    Uma fatura YYYY-MM contém transações em:
    dia 5 de YYYY-MM (inclusive) até dia 5 do mês seguinte (exclusivo).

    Exemplos:
    - 04/08/2026 -> ciclo 2026-07
    - 05/08/2026 -> ciclo 2026-08
    - 04/09/2026 -> ciclo 2026-08
    - 05/09/2026 -> ciclo 2026-09

    A classificação usa a data real da transação e ignora dueDate,
    billDate e billForecastDate, pois esses campos podem representar
    vencimento/fatura e deslocar compras antigas para outro mês.
    """
    transaction_date = parse_transaction_date(transaction)
    if transaction_date is None:
        return None

    if transaction_date.day >= BILLING_CYCLE_DAY:
        return _month_key(
            transaction_date.year,
            transaction_date.month,
        )

    year, month = _previous_month(transaction_date)
    return _month_key(year, month)


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
    """Retorna todos os PIX do mês-calendário, entradas e saídas."""
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
    month: str,
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
            if _credit_card_cycle_month(transaction) != month:
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
                    "date": _transaction_date_iso(transaction),
                    "competence_month": month,
                    "billing_cycle_day": BILLING_CYCLE_DAY,
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


@router.get("/monthly-breakdown")
def get_monthly_breakdown(
    month: str = Query(
        ...,
        description="Competência no formato YYYY-MM",
        examples=["2026-09"],
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month = _validate_month(month)

    snapshot = (
        db.query(FinancialSnapshot)
        .filter(FinancialSnapshot.user_id == current_user.id)
        .first()
    )

    payload = deepcopy(snapshot.payload or {}) if snapshot else {}
    accounts = payload.get("accounts") or []

    pix_items = build_pix_breakdown(accounts, month)
    card_items = build_credit_card_breakdown(accounts, month)

    pix_sent_total = round(
        sum(
            float(item["amount"])
            for item in pix_items
            if item.get("direction") == "OUT"
        ),
        2,
    )
    pix_received_total = round(
        sum(
            float(item["amount"])
            for item in pix_items
            if item.get("direction") == "IN"
        ),
        2,
    )
    pix_net = round(
        pix_received_total - pix_sent_total,
        2,
    )

    pix_sent_count = sum(
        1 for item in pix_items if item.get("direction") == "OUT"
    )
    pix_received_count = sum(
        1 for item in pix_items if item.get("direction") == "IN"
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
            "billing_cycle_day": BILLING_CYCLE_DAY,
            "items": card_items,
        },
        "pix": {
            # Mantido para compatibilidade com o app atual.
            "total": pix_sent_total,
            "sent_total": pix_sent_total,
            "received_total": pix_received_total,
            "net": pix_net,
            "count": len(pix_items),
            "sent_count": pix_sent_count,
            "received_count": pix_received_count,
            "items": pix_items,
        },
        # O comprometimento continua considerando apenas saídas PIX.
        "total_committed": round(card_total + pix_sent_total, 2),
        "updated_at": (
            snapshot.updated_at.isoformat()
            if snapshot and snapshot.updated_at
            else None
        ),
    }
