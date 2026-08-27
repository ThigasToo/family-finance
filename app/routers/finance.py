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
# HELPERS - NORMALIZAÇÃO DE INSTITUIÇÕES
# =========================================================


def normalize_institution_name(
    name: str | None,
) -> str | None:
    if not name:
        return None

    cleaned = name.strip()

    if not cleaned:
        return None

    normalized = cleaned.upper()

    if (
        "PICPAY" in normalized
        or "PIC PAY" in normalized
    ):
        return "PicPay"

    if (
        "NUBANK" in normalized
        or "NU PAGAMENTOS" in normalized
        or "NU FINANCEIRA" in normalized
    ):
        return "Nubank"

    if (
        "ITAU" in normalized
        or "ITAÚ" in normalized
    ):
        return "Itaú"

    if (
        "BANCO INTER" in normalized
        or normalized == "INTER"
    ):
        return "Inter"

    if "BTG" in normalized:
        return "BTG Pactual"

    if (
        "XP INVESTIMENTOS" in normalized
        or normalized == "XP"
    ):
        return "XP"

    if "BRADESCO" in normalized:
        return "Bradesco"

    if (
        "BANCO DO BRASIL" in normalized
        or normalized == "BB"
    ):
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

    if (
        "C6 BANK" in normalized
        or "BANCO C6" in normalized
    ):
        return "C6 Bank"

    if (
        "MERCADO PAGO" in normalized
        or "MERCADOPAGO" in normalized
    ):
        return "Mercado Pago"

    if (
        "PAGBANK" in normalized
        or "PAGSEGURO" in normalized
    ):
        return "PagBank"

    return cleaned


# =========================================================
# HELPERS - CONTAS / CARTÕES
# =========================================================


def resolve_account_institution(
    account: dict,
    fallback: str | None = None,
) -> str:
    candidates = [
        account.get("marketingName"),
        account.get("name"),
    ]

    for candidate in candidates:
        normalized = normalize_institution_name(
            candidate
        )

        if normalized:
            return normalized

    normalized_fallback = (
        normalize_institution_name(
            fallback
        )
    )

    if normalized_fallback:
        return normalized_fallback

    return "Outros"


# =========================================================
# HELPERS - INVESTIMENTOS PLUGGY
# =========================================================


def resolve_investment_institution(
    investment: dict,
    fallback: str | None = None,
) -> str:
    institution = investment.get(
        "institution"
    )

    if isinstance(
        institution,
        dict,
    ):
        name = institution.get(
            "name"
        )

        normalized = (
            normalize_institution_name(
                name
            )
        )

        if normalized:
            return normalized

    if isinstance(
        institution,
        str,
    ):
        normalized = (
            normalize_institution_name(
                institution
            )
        )

        if normalized:
            return normalized

    issuer = investment.get(
        "issuer"
    )

    normalized_issuer = (
        normalize_institution_name(
            issuer
        )
    )

    if normalized_issuer:
        return normalized_issuer

    normalized_fallback = (
        normalize_institution_name(
            fallback
        )
    )

    if normalized_fallback:
        return normalized_fallback

    return "Outros"


# =========================================================
# HELPERS - PIX
# =========================================================


def normalize_text(
    value,
) -> str:
    if value is None:
        return ""

    return str(value).strip().upper()


def is_pix_transaction(
    transaction: dict,
) -> bool:
    """
    Identifica se uma transação é PIX.

    Priorizamos campos estruturados da Pluggy
    e usamos descrição apenas como fallback.
    """

    payment_data = (
        transaction.get("paymentData")
        or {}
    )

    if isinstance(
        payment_data,
        dict,
    ):
        payment_method = (
            normalize_text(
                payment_data.get(
                    "paymentMethod"
                )
            )
        )

        if payment_method == "PIX":
            return True

    operation_type = normalize_text(
        transaction.get(
            "operationType"
        )
    )

    if operation_type == "PIX":
        return True

    category = normalize_text(
        transaction.get(
            "category"
        )
    )

    if "PIX" in category:
        return True

    description = normalize_text(
        transaction.get(
            "description"
        )
    )

    description_raw = normalize_text(
        transaction.get(
            "descriptionRaw"
        )
    )

    if (
        "PIX" in description
        or "PIX" in description_raw
    ):
        return True

    return False


def is_outflow_transaction(
    transaction: dict,
) -> bool:
    """
    Para contas BANK, a Pluggy usa:
    DEBIT = saída
    CREDIT = entrada

    Mantemos também fallback pelo sinal do amount.
    """

    transaction_type = normalize_text(
        transaction.get(
            "type"
        )
    )

    if transaction_type == "DEBIT":
        return True

    if transaction_type == "CREDIT":
        return False

    amount = transaction.get(
        "amount"
    )

    if isinstance(
        amount,
        (int, float),
    ):
        return amount < 0

    try:
        return float(amount) < 0
    except (
        TypeError,
        ValueError,
    ):
        return False


def is_pix_sent(
    transaction: dict,
) -> bool:
    """
    PIX enviado = transação PIX + saída da conta.
    """

    return (
        is_pix_transaction(
            transaction
        )
        and is_outflow_transaction(
            transaction
        )
    )


def transaction_amount_abs(
    transaction: dict,
) -> float:
    amount = transaction.get(
        "amount"
    )

    try:
        return abs(
            float(amount)
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0.0


def parse_transaction_date(
    transaction: dict,
) -> datetime | None:
    raw_date = transaction.get(
        "date"
    )

    if not raw_date:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(raw_date).replace(
                "Z",
                "+00:00",
            )
        )

        return parsed
    except ValueError:
        return None


def calculate_pix_sent_current_month(
    accounts: list,
) -> float:
    """
    Soma PIX enviados em contas BANK
    no mês atual.

    Não considera cartões.
    """

    now = datetime.now(
        timezone.utc
    )

    total = 0.0

    for account in accounts:
        if normalize_text(
            account.get("type")
        ) != "BANK":
            continue

        transactions = (
            account.get(
                "transactions"
            )
            or []
        )

        for transaction in transactions:
            if not is_pix_sent(
                transaction
            ):
                continue

            transaction_date = (
                parse_transaction_date(
                    transaction
                )
            )

            if transaction_date is None:
                continue

            if (
                transaction_date.year
                != now.year
            ):
                continue

            if (
                transaction_date.month
                != now.month
            ):
                continue

            total += (
                transaction_amount_abs(
                    transaction
                )
            )

    return round(
        total,
        2,
    )


def enrich_transaction(
    transaction: dict,
) -> dict:
    """
    Adiciona campos nossos ao payload
    sem remover os dados originais da Pluggy.
    """

    transaction[
        "is_pix"
    ] = is_pix_transaction(
        transaction
    )

    transaction[
        "is_pix_sent"
    ] = is_pix_sent(
        transaction
    )

    return transaction


# =========================================================
# HELPERS - INVESTIMENTOS MANUAIS
# =========================================================


def manual_investment_to_summary(
    investment: ManualInvestment,
) -> dict:
    institution_name = (
        normalize_institution_name(
            investment.institution
        )
        or investment.institution
    )

    return {
        "id": (
            f"manual-{investment.id}"
        ),

        "manual_id":
            investment.id,

        "name":
            investment.name,

        "type":
            investment.type,

        "institution":
            institution_name,

        "institution_name":
            institution_name,

        "resolved_institution":
            institution_name,

        "balance": float(
            investment.current_value
        ),

        "current_value": float(
            investment.current_value
        ),

        "quantity": (
            float(
                investment.quantity
            )
            if investment.quantity
            is not None
            else None
        ),

        "average_price": (
            float(
                investment.average_price
            )
            if investment.average_price
            is not None
            else None
        ),

        "invested_value": (
            float(
                investment.invested_value
            )
            if investment.invested_value
            is not None
            else None
        ),

        "currency":
            investment.currency,

        "ticker":
            investment.ticker,

        "source":
            "MANUAL",

        "created_at": (
            investment
            .created_at
            .isoformat()
            if investment.created_at
            else None
        ),

        "updated_at": (
            investment
            .updated_at
            .isoformat()
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
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(
        get_db
    ),
):
    snapshot = (
        db.query(
            FinancialSnapshot
        )
        .filter(
            FinancialSnapshot.user_id
            == current_user.id
        )
        .first()
    )

    if snapshot:
        payload = deepcopy(
            snapshot.payload or {}
        )

        updated_at = (
            snapshot.updated_at
        )

    else:
        payload = {
            "accounts": [],
            "investments": [],
        }

        updated_at = None

    payload.setdefault(
        "accounts",
        [],
    )

    payload.setdefault(
        "investments",
        [],
    )

    # =====================================================
    # PIX ENVIADOS NO MÊS
    # =====================================================

    pix_sent_current_month = (
        calculate_pix_sent_current_month(
            payload[
                "accounts"
            ]
        )
    )

    payload[
        "pix_sent_current_month"
    ] = pix_sent_current_month

    # =====================================================
    # INVESTIMENTOS MANUAIS
    # =====================================================

    manual_investments = (
        db.query(
            ManualInvestment
        )
        .filter(
            ManualInvestment.user_id
            == current_user.id
        )
        .all()
    )

    for investment in manual_investments:
        payload[
            "investments"
        ].append(
            manual_investment_to_summary(
                investment
            )
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
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(
        get_db
    ),
):
    snapshot = (
        db.query(
            FinancialSnapshot
        )
        .filter(
            FinancialSnapshot.user_id
            == current_user.id
        )
        .first()
    )

    # =====================================================
    # COOLDOWN
    # =====================================================

    if (
        snapshot
        and snapshot.updated_at
    ):
        snapshot_updated_at = (
            snapshot.updated_at
        )

        if (
            snapshot_updated_at.tzinfo
            is None
        ):
            snapshot_updated_at = (
                snapshot_updated_at.replace(
                    tzinfo=timezone.utc
                )
            )

        elapsed = (
            datetime.now(
                timezone.utc
            )
            - snapshot_updated_at
        )

        if elapsed < timedelta(
            minutes=COOLDOWN_MINUTES
        ):
            wait_seconds = int(
                (
                    timedelta(
                        minutes=
                            COOLDOWN_MINUTES
                    )
                    - elapsed
                ).total_seconds()
            )

            raise HTTPException(
                status_code=429,
                detail=(
                    f"Aguarde "
                    f"{wait_seconds}s "
                    f"antes de atualizar "
                    f"novamente"
                ),
            )

    # =====================================================
    # ITENS PLUGGY
    # =====================================================

    items = (
        db.query(
            PluggyItem
        )
        .filter(
            PluggyItem.user_id
            == current_user.id
        )
        .all()
    )

    all_accounts = []
    all_investments = []

    # =====================================================
    # PROCESSAMENTO
    # =====================================================

    for item in items:

        # =================================================
        # CONTAS / CARTÕES
        # =================================================

        accounts = (
            await fetch_accounts(
                item.item_id
            )
        )

        for account in accounts:

            institution_name = (
                resolve_account_institution(
                    account,
                    fallback=
                        item.institution_name,
                )
            )

            account[
                "institution_name"
            ] = institution_name

            account[
                "resolved_institution"
            ] = institution_name

            account[
                "source"
            ] = "PLUGGY"

            if account.get(
                "type"
            ) in (
                "BANK",
                "CREDIT",
            ):
                try:
                    transactions = (
                        await fetch_transactions(
                            account[
                                "id"
                            ]
                        )
                    )

                    # =====================================
                    # ENRIQUECIMENTO PIX
                    # =====================================

                    enriched_transactions = []

                    for transaction in transactions:
                        enriched_transactions.append(
                            enrich_transaction(
                                transaction
                            )
                        )

                    transactions = (
                        enriched_transactions
                    )

                except Exception as exc:
                    print(
                        "Erro ao buscar "
                        "transações da conta "
                        f"{account.get('id')}: "
                        f"{exc}"
                    )

                    transactions = []

                account[
                    "transactions"
                ] = transactions

            else:
                account[
                    "transactions"
                ] = []

        all_accounts.extend(
            accounts
        )

        # =================================================
        # INVESTIMENTOS
        # =================================================

        investments = (
            await fetch_investments(
                item.item_id
            )
        )

        for investment in investments:

            institution_name = (
                resolve_investment_institution(
                    investment,
                    fallback=
                        item.institution_name,
                )
            )

            investment[
                "institution_name"
            ] = institution_name

            investment[
                "resolved_institution"
            ] = institution_name

            investment[
                "source"
            ] = "PLUGGY"

        all_investments.extend(
            investments
        )

    # =====================================================
    # SNAPSHOT
    # =====================================================

    payload = {
        "accounts":
            all_accounts,

        "investments":
            all_investments,
    }

    now = datetime.now(
        timezone.utc
    )

    if snapshot:
        snapshot.payload = payload
        snapshot.updated_at = now

    else:
        snapshot = (
            FinancialSnapshot(
                user_id=
                    current_user.id,

                payload=payload,

                updated_at=now,
            )
        )

        db.add(
            snapshot
        )

    db.commit()

    return FinanceRefreshOut(
        status="ok",
        updated_at=now,
    )