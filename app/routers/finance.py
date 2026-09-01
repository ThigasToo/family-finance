from copy import deepcopy

from datetime import (
    datetime,
    timedelta,
    timezone,
)

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    User,
    PluggyItem,
    FinancialSnapshot,
    ManualInvestment,
)
from app.security import get_current_user
from app.schemas import (
    FinanceSummaryOut,
    FinanceRefreshOut,
)
from app.pluggy_client import (
    fetch_accounts,
    fetch_transactions,
    fetch_investments,
)


router = APIRouter(
    prefix="/finance",
    tags=["finance"],
)

COOLDOWN_MINUTES = 5


# =========================================================
# HELPERS - TEXTO / INSTITUIÇÕES
# =========================================================


def normalize_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def normalize_institution_name(
    name: str | None,
) -> str | None:
    if not name:
        return None

    cleaned = name.strip()
    if not cleaned:
        return None

    normalized = cleaned.upper()

    if "PICPAY" in normalized or "PIC PAY" in normalized:
        return "PicPay"
    if (
        "NUBANK" in normalized
        or "NU PAGAMENTOS" in normalized
        or "NU FINANCEIRA" in normalized
    ):
        return "Nubank"
    if "ITAU" in normalized or "ITAÚ" in normalized:
        return "Itaú"
    if "BANCO INTER" in normalized or normalized == "INTER":
        return "Inter"
    if "BTG" in normalized:
        return "BTG Pactual"
    if "XP INVESTIMENTOS" in normalized or normalized == "XP":
        return "XP"
    if "BRADESCO" in normalized:
        return "Bradesco"
    if "BANCO DO BRASIL" in normalized or normalized == "BB":
        return "Banco do Brasil"
    if "SANTANDER" in normalized:
        return "Santander"
    if (
        "CAIXA ECONOMICA" in normalized
        or "CAIXA ECONÔMICA" in normalized
    ):
        return "Caixa"
    if "SAFRA" in normalized:
        return "Safra"
    if "C6 BANK" in normalized or "BANCO C6" in normalized:
        return "C6 Bank"
    if "MERCADO PAGO" in normalized or "MERCADOPAGO" in normalized:
        return "Mercado Pago"
    if "PAGBANK" in normalized or "PAGSEGURO" in normalized:
        return "PagBank"

    return cleaned


def resolve_account_institution(
    account: dict,
    fallback: str | None = None,
) -> str:
    candidates = [
        account.get("marketingName"),
        account.get("name"),
    ]

    for candidate in candidates:
        normalized = normalize_institution_name(candidate)
        if normalized:
            return normalized

    normalized_fallback = normalize_institution_name(fallback)
    if normalized_fallback:
        return normalized_fallback

    return "Outros"


def resolve_investment_institution(
    investment: dict,
    fallback: str | None = None,
) -> str:
    institution = investment.get("institution")

    if isinstance(institution, dict):
        normalized = normalize_institution_name(
            institution.get("name")
        )
        if normalized:
            return normalized

    if isinstance(institution, str):
        normalized = normalize_institution_name(institution)
        if normalized:
            return normalized

    normalized_issuer = normalize_institution_name(
        investment.get("issuer")
    )
    if normalized_issuer:
        return normalized_issuer

    normalized_fallback = normalize_institution_name(fallback)
    if normalized_fallback:
        return normalized_fallback

    return "Outros"


# =========================================================
# HELPERS - TRANSAÇÕES / PIX
# =========================================================


def parse_transaction_date(
    transaction: dict,
) -> datetime | None:
    candidates = [
        transaction.get("date"),
        transaction.get("transactionDate"),
        transaction.get("createdAt"),
    ]

    for raw_date in candidates:
        if not raw_date:
            continue

        try:
            return datetime.fromisoformat(
                str(raw_date).replace("Z", "+00:00")
            )
        except ValueError:
            continue

    return None


def transaction_amount_abs(
    transaction: dict,
) -> float:
    for key in ("amount", "value"):
        amount = transaction.get(key)
        try:
            if amount is not None:
                return abs(float(amount))
        except (TypeError, ValueError):
            continue

    return 0.0


def month_key_from_datetime(
    value: datetime,
) -> str:
    return f"{value.year}-{value.month:02d}"


def is_pix_transaction(
    transaction: dict,
) -> bool:
    payment_data = transaction.get("paymentData") or {}

    if isinstance(payment_data, dict):
        payment_method = normalize_text(
            payment_data.get("paymentMethod")
        )
        if payment_method == "PIX":
            return True

    operation_type = normalize_text(
        transaction.get("operationType")
    )
    if operation_type == "PIX":
        return True

    category = normalize_text(transaction.get("category"))
    if "PIX" in category:
        return True

    description = normalize_text(
        transaction.get("description")
    )
    description_raw = normalize_text(
        transaction.get("descriptionRaw")
    )

    return "PIX" in description or "PIX" in description_raw


def is_outflow_transaction(
    transaction: dict,
) -> bool:
    transaction_type = normalize_text(
        transaction.get("type")
    )

    if transaction_type == "DEBIT":
        return True
    if transaction_type == "CREDIT":
        return False

    amount = transaction.get("amount")
    try:
        return float(amount) < 0
    except (TypeError, ValueError):
        return False


def is_same_person_transfer(
    transaction: dict,
) -> bool:
    """Identifica transferências entre contas do próprio titular."""

    category = normalize_text(transaction.get("category"))
    if category in {
        "SAME PERSON TRANSFER",
        "SAME_PERSON_TRANSFER",
    }:
        return True

    return False


def is_pix_sent(
    transaction: dict,
) -> bool:
    return (
        is_pix_transaction(transaction)
        and is_outflow_transaction(transaction)
        and not is_same_person_transfer(transaction)
    )


def enrich_transaction(
    transaction: dict,
) -> dict:
    enriched = deepcopy(transaction)
    enriched["is_pix"] = is_pix_transaction(enriched)
    enriched["is_pix_sent"] = is_pix_sent(enriched)
    return enriched


def calculate_pix_sent_by_month(
    accounts: list,
) -> dict[str, float]:
    monthly: dict[str, float] = {}

    for account in accounts:
        if normalize_text(account.get("type")) != "BANK":
            continue

        for transaction in account.get("transactions") or []:
            if not isinstance(transaction, dict):
                continue
            if not is_pix_sent(transaction):
                continue

            transaction_date = parse_transaction_date(transaction)
            if transaction_date is None:
                continue

            key = month_key_from_datetime(transaction_date)
            monthly[key] = (
                monthly.get(key, 0.0)
                + transaction_amount_abs(transaction)
            )

    return {
        key: round(value, 2)
        for key, value in monthly.items()
    }


def calculate_pix_sent_current_month(
    accounts: list,
) -> float:
    now = datetime.now(timezone.utc)
    monthly = calculate_pix_sent_by_month(accounts)
    return monthly.get(month_key_from_datetime(now), 0.0)


# =========================================================
# HELPERS - CARTÃO POR COMPETÊNCIA
# =========================================================


def is_credit_card_purchase(
    transaction: dict,
) -> bool:
    combined = " ".join(
        [
            normalize_text(transaction.get("type")),
            normalize_text(transaction.get("category")),
            normalize_text(transaction.get("description")),
            normalize_text(transaction.get("descriptionRaw")),
        ]
    )

    excluded_terms = (
        "PAYMENT",
        "PAGAMENTO",
        "PAGAMENTO DE FATURA",
        "REFUND",
        "ESTORNO",
        "REVERSAL",
    )

    return not any(term in combined for term in excluded_terms)


def get_credit_card_month_key(
    transaction: dict,
) -> str | None:
    """
    Prioriza a competência de fatura informada pela Pluggy.
    Se ela não existir, usa a data da própria parcela/transação.
    """

    metadata = transaction.get("creditCardMetadata") or {}

    if isinstance(metadata, dict):
        for field in (
            "billForecastDate",
            "billDate",
            "dueDate",
        ):
            raw = metadata.get(field)
            if not raw:
                continue

            raw_text = str(raw).strip()
            if len(raw_text) >= 7:
                return raw_text[:7]

    transaction_date = parse_transaction_date(transaction)
    if transaction_date is None:
        return None

    return month_key_from_datetime(transaction_date)


def calculate_credit_card_commitments_by_month(
    accounts: list,
) -> dict[str, float]:
    """
    Soma as parcelas/transações de cartão por competência mensal.

    O `amount` de cada transação é usado como compromisso daquele
    mês; o valor total parcelado não é somado novamente.
    """

    monthly: dict[str, float] = {}

    for account in accounts:
        if normalize_text(account.get("type")) != "CREDIT":
            continue

        for transaction in account.get("transactions") or []:
            if not isinstance(transaction, dict):
                continue
            if not is_credit_card_purchase(transaction):
                continue

            key = get_credit_card_month_key(transaction)
            if key is None:
                continue

            amount = transaction_amount_abs(transaction)
            if amount <= 0:
                continue

            monthly[key] = monthly.get(key, 0.0) + amount

    return {
        key: round(value, 2)
        for key, value in monthly.items()
    }


# =========================================================
# HELPERS - INVESTIMENTOS
# =========================================================


def investment_current_value(
    investment: dict,
) -> float:
    candidates = [
        investment.get("balance"),
        investment.get("currentValue"),
        investment.get("current_value"),
        investment.get("amount"),
    ]

    for value in candidates:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue

    return 0.0


def is_active_pluggy_investment(
    investment: dict,
) -> bool:
    return abs(investment_current_value(investment)) > 0.01


def manual_investment_to_summary(
    investment: ManualInvestment,
) -> dict:
    institution_name = (
        normalize_institution_name(investment.institution)
        or investment.institution
    )

    return {
        "id": f"manual-{investment.id}",
        "manual_id": investment.id,
        "name": investment.name,
        "type": investment.type,
        "institution": institution_name,
        "institution_name": institution_name,
        "resolved_institution": institution_name,
        "balance": float(investment.current_value),
        "current_value": float(investment.current_value),
        "quantity": (
            float(investment.quantity)
            if investment.quantity is not None
            else None
        ),
        "average_price": (
            float(investment.average_price)
            if investment.average_price is not None
            else None
        ),
        "invested_value": (
            float(investment.invested_value)
            if investment.invested_value is not None
            else None
        ),
        "currency": investment.currency,
        "ticker": investment.ticker,
        "source": "MANUAL",
        "created_at": (
            investment.created_at.isoformat()
            if investment.created_at
            else None
        ),
        "updated_at": (
            investment.updated_at.isoformat()
            if investment.updated_at
            else None
        ),
    }


# =========================================================
# SUMMARY
# =========================================================


@router.get(
    "/summary",
    response_model=FinanceSummaryOut,
)
def get_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    snapshot = (
        db.query(FinancialSnapshot)
        .filter(FinancialSnapshot.user_id == current_user.id)
        .first()
    )

    if snapshot:
        payload = deepcopy(snapshot.payload or {})
        updated_at = snapshot.updated_at
    else:
        payload = {
            "accounts": [],
            "investments": [],
        }
        updated_at = None

    payload.setdefault("accounts", [])
    payload.setdefault("investments", [])

    payload["investments"] = [
        investment
        for investment in payload["investments"]
        if (
            normalize_text(investment.get("source")) != "PLUGGY"
            or is_active_pluggy_investment(investment)
        )
    ]

    pix_sent_by_month = calculate_pix_sent_by_month(
        payload["accounts"]
    )
    payload["pix_sent_by_month"] = pix_sent_by_month

    now = datetime.now(timezone.utc)
    payload["pix_sent_current_month"] = pix_sent_by_month.get(
        month_key_from_datetime(now),
        0.0,
    )

    payload["credit_card_commitments_by_month"] = (
        calculate_credit_card_commitments_by_month(
            payload["accounts"]
        )
    )

    manual_investments = (
        db.query(ManualInvestment)
        .filter(ManualInvestment.user_id == current_user.id)
        .all()
    )

    for investment in manual_investments:
        payload["investments"].append(
            manual_investment_to_summary(investment)
        )

    return FinanceSummaryOut(
        payload=payload,
        updated_at=updated_at,
    )


# =========================================================
# REFRESH
# =========================================================


@router.post(
    "/refresh",
    response_model=FinanceRefreshOut,
)
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
        snapshot_updated_at = snapshot.updated_at

        if snapshot_updated_at.tzinfo is None:
            snapshot_updated_at = snapshot_updated_at.replace(
                tzinfo=timezone.utc
            )

        elapsed = datetime.now(timezone.utc) - snapshot_updated_at

        if elapsed < timedelta(minutes=COOLDOWN_MINUTES):
            wait_seconds = int(
                (
                    timedelta(minutes=COOLDOWN_MINUTES)
                    - elapsed
                ).total_seconds()
            )

            raise HTTPException(
                status_code=429,
                detail=(
                    f"Aguarde {wait_seconds}s antes de "
                    "atualizar novamente"
                ),
            )

    items = (
        db.query(PluggyItem)
        .filter(PluggyItem.user_id == current_user.id)
        .all()
    )

    previous_payload = (
        deepcopy(snapshot.payload or {})
        if snapshot
        else {}
    )
    previous_accounts_by_id = {
        account.get("id"): account
        for account in previous_payload.get("accounts", [])
        if account.get("id")
    }

    all_accounts = []
    all_investments = []
    now = datetime.now(timezone.utc)

    for item in items:
        accounts = await fetch_accounts(item.item_id)

        for account in accounts:
            institution_name = resolve_account_institution(
                account,
                fallback=item.institution_name,
            )

            account["institution_name"] = institution_name
            account["resolved_institution"] = institution_name
            account["source"] = "PLUGGY"

            account_type = normalize_text(account.get("type"))

            if account_type in ("BANK", "CREDIT"):
                try:
                    if account_type == "CREDIT":
                        transactions = await fetch_transactions(
                            account["id"],
                            date_from=now - timedelta(days=365),
                            date_to=now + timedelta(days=365),
                        )
                    else:
                        transactions = await fetch_transactions(
                            account["id"],
                            date_from=now - timedelta(days=365),
                            date_to=now,
                        )

                    account["transactions"] = [
                        enrich_transaction(transaction)
                        for transaction in transactions
                    ]

                except Exception as exc:
                    print(
                        "Erro ao buscar transações da conta "
                        f"{account.get('id')}: {exc}"
                    )

                    previous_account = previous_accounts_by_id.get(
                        account.get("id"),
                        {},
                    )
                    account["transactions"] = deepcopy(
                        previous_account.get("transactions") or []
                    )
            else:
                account["transactions"] = []

        all_accounts.extend(accounts)

        investments = await fetch_investments(item.item_id)

        investments = [
            investment
            for investment in investments
            if is_active_pluggy_investment(investment)
        ]

        for investment in investments:
            institution_name = resolve_investment_institution(
                investment,
                fallback=item.institution_name,
            )

            investment["institution_name"] = institution_name
            investment["resolved_institution"] = institution_name
            investment["source"] = "PLUGGY"

        all_investments.extend(investments)

    payload = {
        "accounts": all_accounts,
        "investments": all_investments,
    }

    if snapshot:
        snapshot.payload = payload
        snapshot.updated_at = now
    else:
        snapshot = FinancialSnapshot(
            user_id=current_user.id,
            payload=payload,
            updated_at=now,
        )
        db.add(snapshot)

    db.commit()

    return FinanceRefreshOut(
        status="ok",
        updated_at=now,
    )
