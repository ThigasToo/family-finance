from calendar import monthrange
from copy import deepcopy
from datetime import date, datetime

from app.routers.finance import (
    is_credit_card_purchase,
    normalize_text,
    parse_transaction_date,
    resolve_account_institution,
    transaction_amount_abs,
)


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
        or "Cartão"
    )


def _description(transaction: dict) -> str:
    return (
        _first_non_empty(
            transaction.get("description"),
            transaction.get("descriptionRaw"),
            transaction.get("merchant"),
        )
        or "Lançamento"
    )


def _installment(transaction: dict) -> tuple[int | None, int | None, float | None]:
    metadata = transaction.get("creditCardMetadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    def pick(keys):
        for key in keys:
            if metadata.get(key) is not None:
                return metadata.get(key)
            if transaction.get(key) is not None:
                return transaction.get(key)
        return None

    current = pick((
        "installmentNumber",
        "installment_number",
        "currentInstallment",
        "current_installment",
    ))
    total = pick((
        "totalInstallments",
        "total_installments",
        "installments",
        "installmentCount",
        "installment_count",
    ))
    total_amount = pick(("totalAmount", "total_amount"))

    try:
        current = int(current) if current is not None else None
    except (TypeError, ValueError):
        current = None
    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None
    try:
        total_amount = float(total_amount) if total_amount is not None else None
    except (TypeError, ValueError):
        total_amount = None

    return current, total, total_amount


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _series_key(account: dict, transaction: dict, total: int, total_amount: float | None):
    description = normalize_text(_description(transaction))
    amount = round(transaction_amount_abs(transaction), 2)
    total_value = round(total_amount, 2) if total_amount is not None else None
    return (
        str(account.get("id") or ""),
        description,
        total,
        total_value,
        amount,
    )


def _real_item(account: dict, transaction: dict) -> dict | None:
    if not is_credit_card_purchase(transaction):
        return None
    transaction_date = parse_transaction_date(transaction)
    if transaction_date is None:
        return None
    amount = transaction_amount_abs(transaction)
    if amount <= 0:
        return None

    current, total, total_amount = _installment(transaction)
    metadata = transaction.get("creditCardMetadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    return {
        "id": transaction.get("id"),
        "institution": resolve_account_institution(
            account,
            fallback=account.get("institution_name"),
        ),
        "card_id": account.get("id"),
        "card_name": _account_display_name(account),
        "description": _description(transaction),
        "amount": round(amount, 2),
        "date": transaction_date.isoformat(),
        "installment_number": current,
        "installment_total": total,
        "installment_total_amount": total_amount,
        "bill_id": transaction.get("billId"),
        "status": transaction.get("status"),
        "projected": False,
        "projection_source": None,
        "bill_forecast_date": metadata.get("billForecastDate"),
        "bill_date": metadata.get("billDate"),
        "due_date": metadata.get("dueDate"),
    }


def build_card_schedule(accounts: list) -> list[dict]:
    real_items: list[dict] = []
    series_latest: dict[tuple, tuple[dict, dict]] = {}
    real_installments: set[tuple] = set()

    for account in accounts:
        if normalize_text(account.get("type")) != "CREDIT":
            continue
        for transaction in account.get("transactions") or []:
            if not isinstance(transaction, dict):
                continue
            item = _real_item(account, transaction)
            if item is None:
                continue
            real_items.append(item)

            current = item.get("installment_number")
            total = item.get("installment_total")
            if current is None or total is None or total <= 1:
                continue
            key = _series_key(
                account,
                transaction,
                total,
                item.get("installment_total_amount"),
            )
            real_installments.add((key, current))
            previous = series_latest.get(key)
            if previous is None or current > previous[0].get("installment_number", 0):
                series_latest[key] = (item, transaction)

    projected: list[dict] = []
    for key, (latest, transaction) in series_latest.items():
        current = latest.get("installment_number")
        total = latest.get("installment_total")
        if current is None or total is None or current >= total:
            continue

        base_dt = parse_transaction_date(transaction)
        if base_dt is None:
            continue
        base_date = base_dt.date()

        for future_number in range(current + 1, total + 1):
            if (key, future_number) in real_installments:
                continue
            projected_date = _add_months(base_date, future_number - current)
            item = deepcopy(latest)
            item.update(
                {
                    "id": f"projected:{latest.get('card_id')}:{future_number}:{key[1]}",
                    "date": datetime.combine(projected_date, datetime.min.time()).isoformat(),
                    "installment_number": future_number,
                    "projected": True,
                    "projection_source": "installment",
                    "bill_id": None,
                    "status": "PROJECTED",
                    "bill_forecast_date": None,
                    "bill_date": None,
                    "due_date": None,
                }
            )
            projected.append(item)

    items = real_items + projected
    items.sort(key=lambda item: item.get("date") or "")
    return items


def filter_card_schedule(
    accounts: list,
    date_from: date,
    date_to: date,
) -> list[dict]:
    result = []
    for item in build_card_schedule(accounts):
        raw = item.get("date")
        if not raw:
            continue
        try:
            item_date = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if date_from <= item_date <= date_to:
            result.append(item)
    result.sort(key=lambda item: item.get("date") or "", reverse=True)
    return result


def next_due_summary(account: dict, today: date | None = None) -> dict:
    today = today or date.today()
    bills = [bill for bill in (account.get("bills") or []) if isinstance(bill, dict)]

    candidates = []
    for bill in bills:
        raw = bill.get("dueDate")
        if not raw:
            continue
        try:
            due = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if due >= today:
            candidates.append((due, bill))

    if candidates:
        due, bill = min(candidates, key=lambda item: item[0])
        return {
            "due_date": due.isoformat(),
            "source": "bill",
            "estimated": False,
            "bill_id": bill.get("id"),
            "bill_total": bill.get("totalAmount"),
            "minimum_payment": bill.get("minimumPaymentAmount"),
            "closing_date": bill.get("billClosingDate"),
        }

    credit_data = account.get("creditData") or {}
    if not isinstance(credit_data, dict):
        credit_data = {}
    raw_due = credit_data.get("balanceDueDate")
    parsed_due = None
    if raw_due:
        try:
            parsed_due = datetime.fromisoformat(str(raw_due).replace("Z", "+00:00")).date()
        except ValueError:
            parsed_due = None

    if parsed_due and parsed_due >= today:
        return {
            "due_date": parsed_due.isoformat(),
            "source": "creditData",
            "estimated": False,
            "bill_id": None,
            "bill_total": None,
            "minimum_payment": credit_data.get("minimumPayment"),
            "closing_date": None,
        }

    if parsed_due:
        estimated = parsed_due
        while estimated < today:
            estimated = _add_months(estimated, 1)
        return {
            "due_date": estimated.isoformat(),
            "source": "estimated",
            "estimated": True,
            "bill_id": None,
            "bill_total": None,
            "minimum_payment": None,
            "closing_date": None,
        }

    return {
        "due_date": None,
        "source": "unavailable",
        "estimated": False,
        "bill_id": None,
        "bill_total": None,
        "minimum_payment": None,
        "closing_date": None,
    }
