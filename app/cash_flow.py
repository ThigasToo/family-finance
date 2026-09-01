from datetime import datetime

from app.routers.finance import (
    is_outflow_transaction,
    is_pix_transaction,
    is_same_person_transfer,
    normalize_text,
    parse_transaction_date,
    resolve_account_institution,
    transaction_amount_abs,
)


MATCH_TOLERANCE_DAYS = 3
MATCH_TOLERANCE_AMOUNT = 0.02


APPLICATION_TYPES = {
    "BUY",
    "PURCHASE",
    "APPLICATION",
    "APLICACAO",
    "APLICAÇÃO",
    "CONTRIBUTION",
    "DEPOSIT",
}

REDEMPTION_TYPES = {
    "SELL",
    "REDEMPTION",
    "REDEEM",
    "RESGATE",
    "WITHDRAWAL",
}

TRANSFER_TYPES = {
    "TRANSFER",
    "TRANSFER_IN",
    "TRANSFER_OUT",
}


def month_key(value: datetime) -> str:
    return f"{value.year}-{value.month:02d}"


def first_non_empty(*values):
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def account_display_name(account: dict) -> str:
    return (
        first_non_empty(
            account.get("name"),
            account.get("marketingName"),
            account.get("number"),
        )
        or "Conta"
    )


def transaction_description(transaction: dict) -> str:
    return (
        first_non_empty(
            transaction.get("description"),
            transaction.get("descriptionRaw"),
            transaction.get("merchant"),
        )
        or "Lançamento"
    )


def transaction_counterparty(transaction: dict, outflow: bool) -> str | None:
    payment_data = transaction.get("paymentData") or {}
    if not isinstance(payment_data, dict):
        payment_data = {}

    return first_non_empty(
        payment_data.get("receiverName") if outflow else None,
        payment_data.get("payerName") if not outflow else None,
        payment_data.get("receiverName"),
        payment_data.get("payerName"),
        transaction.get("counterpartyName"),
    )


def investment_transaction_date(transaction: dict) -> datetime | None:
    for key in (
        "date",
        "transactionDate",
        "tradeDate",
        "settlementDate",
        "createdAt",
    ):
        raw = transaction.get(key)
        if not raw:
            continue
        try:
            return datetime.fromisoformat(
                str(raw).replace("Z", "+00:00")
            )
        except ValueError:
            continue
    return None


def investment_transaction_amount(transaction: dict) -> float:
    for key in (
        "amount",
        "value",
        "netAmount",
        "grossAmount",
        "totalValue",
    ):
        raw = transaction.get(key)
        if raw is None:
            continue
        try:
            return abs(float(raw))
        except (TypeError, ValueError):
            continue

    quantity = transaction.get("quantity")
    price = first_non_empty(
        transaction.get("unitPrice"),
        transaction.get("price"),
    )
    try:
        if quantity is not None and price is not None:
            return abs(float(quantity) * float(price))
    except (TypeError, ValueError):
        pass

    return 0.0


def investment_transaction_kind(transaction: dict) -> str | None:
    raw = normalize_text(
        first_non_empty(
            transaction.get("type"),
            transaction.get("transactionType"),
            transaction.get("operationType"),
        )
    )

    if raw in APPLICATION_TYPES:
        return "APPLICATION"
    if raw in REDEMPTION_TYPES:
        return "REDEMPTION"
    if raw in TRANSFER_TYPES:
        return "TRANSFER"

    description = normalize_text(
        first_non_empty(
            transaction.get("description"),
            transaction.get("descriptionRaw"),
        )
    )

    if any(term in description for term in ("APLIC", "COMPRA", "BUY")):
        return "APPLICATION"
    if any(term in description for term in ("RESGATE", "VENDA", "SELL", "REDEM")):
        return "REDEMPTION"
    if "TRANSFER" in description:
        return "TRANSFER"

    return None


def _date_distance_days(a: datetime, b: datetime) -> int:
    try:
        return abs((a - b).days)
    except TypeError:
        # Evita erro ao comparar datetime naive com aware.
        return abs((a.replace(tzinfo=None) - b.replace(tzinfo=None)).days)


def _same_amount(a: float, b: float) -> bool:
    return abs(a - b) <= MATCH_TOLERANCE_AMOUNT


def _institution_key(value: str | None) -> str:
    return normalize_text(value).replace(" ", "")


def build_investment_movements(investments: list) -> list[dict]:
    movements: list[dict] = []

    for investment in investments:
        if not isinstance(investment, dict):
            continue

        institution = first_non_empty(
            investment.get("institution_name"),
            investment.get("resolved_institution"),
            investment.get("institution"),
            investment.get("issuer"),
        )
        name = first_non_empty(
            investment.get("name"),
            investment.get("ticker"),
            investment.get("issuer"),
        ) or "Investimento"

        for transaction in investment.get("transactions") or []:
            if not isinstance(transaction, dict):
                continue

            date = investment_transaction_date(transaction)
            amount = investment_transaction_amount(transaction)
            kind = investment_transaction_kind(transaction)

            if date is None or amount <= 0 or kind is None:
                continue

            movements.append(
                {
                    "investment_id": investment.get("id"),
                    "investment_name": name,
                    "institution": institution or "Outros",
                    "institution_key": _institution_key(institution),
                    "date": date,
                    "amount": amount,
                    "kind": kind,
                    "raw": transaction,
                    "matched": False,
                }
            )

    return movements


def _find_investment_match(
    bank_date: datetime,
    bank_amount: float,
    bank_institution: str,
    outflow: bool,
    movements: list[dict],
) -> dict | None:
    wanted = "APPLICATION" if outflow else "REDEMPTION"
    bank_institution_key = _institution_key(bank_institution)

    candidates: list[tuple[int, int, dict]] = []

    for movement in movements:
        if movement.get("matched"):
            continue
        if movement.get("kind") not in {wanted, "TRANSFER"}:
            continue
        if not _same_amount(bank_amount, float(movement["amount"])):
            continue

        distance = _date_distance_days(bank_date, movement["date"])
        if distance > MATCH_TOLERANCE_DAYS:
            continue

        same_institution = (
            bank_institution_key
            and movement.get("institution_key")
            and bank_institution_key == movement.get("institution_key")
        )

        # Prioriza mesma instituição, depois menor distância de data.
        candidates.append((0 if same_institution else 1, distance, movement))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _bank_transaction_rows(accounts: list) -> list[dict]:
    rows: list[dict] = []

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

            date = parse_transaction_date(transaction)
            amount = transaction_amount_abs(transaction)
            if date is None or amount <= 0:
                continue

            outflow = is_outflow_transaction(transaction)
            rows.append(
                {
                    "account": account,
                    "transaction": transaction,
                    "date": date,
                    "amount": amount,
                    "outflow": outflow,
                    "institution": institution,
                    "matched_bank": False,
                }
            )

    return rows


def _pair_own_bank_transfers(rows: list[dict]) -> None:
    for index, row in enumerate(rows):
        if row["matched_bank"]:
            continue

        transaction = row["transaction"]
        if is_same_person_transfer(transaction):
            row["matched_bank"] = True
            continue

        if not is_pix_transaction(transaction):
            continue

        for other in rows[index + 1 :]:
            if other["matched_bank"]:
                continue
            if row["outflow"] == other["outflow"]:
                continue
            if row["account"].get("id") == other["account"].get("id"):
                continue
            if not is_pix_transaction(other["transaction"]):
                continue
            if not _same_amount(row["amount"], other["amount"]):
                continue
            if _date_distance_days(row["date"], other["date"]) > 1:
                continue

            row["matched_bank"] = True
            other["matched_bank"] = True
            break


def build_monthly_cash_flow(
    accounts: list,
    investments: list,
    month: str | None = None,
) -> dict:
    """Classifica PIX externos, transferências próprias e investimentos.

    Regras para o caixa disponível:
    - PIX externo recebido: soma;
    - PIX externo enviado: subtrai;
    - transferência entre contas bancárias próprias: neutra;
    - aplicação em investimento: subtrai (dinheiro deixa o caixa disponível);
    - resgate de investimento: soma (dinheiro volta ao caixa disponível).
    """

    rows = _bank_transaction_rows(accounts)
    _pair_own_bank_transfers(rows)
    investment_movements = build_investment_movements(investments)

    items: list[dict] = []
    matched_investment_ids: set[int] = set()

    for row in rows:
        transaction = row["transaction"]
        is_pix = is_pix_transaction(transaction)
        investment_match = _find_investment_match(
            row["date"],
            row["amount"],
            row["institution"],
            row["outflow"],
            investment_movements,
        )

        classification = None
        impact = 0.0
        investment_name = None

        if investment_match is not None:
            investment_match["matched"] = True
            matched_investment_ids.add(id(investment_match))
            investment_name = investment_match.get("investment_name")
            if row["outflow"]:
                classification = "INVESTMENT_APPLICATION"
                impact = -row["amount"]
            else:
                classification = "INVESTMENT_REDEMPTION"
                impact = row["amount"]
        elif row["matched_bank"] and is_pix:
            classification = "INTERNAL_TRANSFER"
            impact = 0.0
        elif is_pix:
            classification = (
                "EXTERNAL_OUT" if row["outflow"] else "EXTERNAL_IN"
            )
            impact = -row["amount"] if row["outflow"] else row["amount"]
        else:
            continue

        key = month_key(row["date"])
        if month is not None and key != month:
            continue

        items.append(
            {
                "id": transaction.get("id"),
                "month": key,
                "date": row["date"].isoformat(),
                "institution": row["institution"],
                "account_id": row["account"].get("id"),
                "account_name": account_display_name(row["account"]),
                "description": transaction_description(transaction),
                "counterparty": transaction_counterparty(
                    transaction,
                    row["outflow"],
                ),
                "amount": round(row["amount"], 2),
                "impact": round(impact, 2),
                "direction": "OUT" if row["outflow"] else "IN",
                "is_pix": is_pix,
                "classification": classification,
                "investment_name": investment_name,
            }
        )

    # Se a Pluggy trouxe a movimentação do investimento, mas não trouxe o
    # lançamento correspondente na conta bancária, ainda refletimos a
    # aplicação/resgate no caixa para não perder a alocação de liquidez.
    for movement in investment_movements:
        if movement.get("matched"):
            continue
        if movement.get("kind") not in {"APPLICATION", "REDEMPTION"}:
            continue

        key = month_key(movement["date"])
        if month is not None and key != month:
            continue

        is_application = movement["kind"] == "APPLICATION"
        impact = -movement["amount"] if is_application else movement["amount"]

        items.append(
            {
                "id": None,
                "month": key,
                "date": movement["date"].isoformat(),
                "institution": movement.get("institution") or "Outros",
                "account_id": None,
                "account_name": "Investimentos",
                "description": (
                    "Aplicação em investimento"
                    if is_application
                    else "Resgate de investimento"
                ),
                "counterparty": None,
                "amount": round(movement["amount"], 2),
                "impact": round(impact, 2),
                "direction": "OUT" if is_application else "IN",
                "is_pix": False,
                "classification": (
                    "INVESTMENT_APPLICATION"
                    if is_application
                    else "INVESTMENT_REDEMPTION"
                ),
                "investment_name": movement.get("investment_name"),
            }
        )

    items.sort(key=lambda item: item.get("date") or "", reverse=True)

    external_in = round(
        sum(item["amount"] for item in items if item["classification"] == "EXTERNAL_IN"),
        2,
    )
    external_out = round(
        sum(item["amount"] for item in items if item["classification"] == "EXTERNAL_OUT"),
        2,
    )
    applications = round(
        sum(
            item["amount"]
            for item in items
            if item["classification"] == "INVESTMENT_APPLICATION"
        ),
        2,
    )
    redemptions = round(
        sum(
            item["amount"]
            for item in items
            if item["classification"] == "INVESTMENT_REDEMPTION"
        ),
        2,
    )
    internal = round(
        sum(
            item["amount"]
            for item in items
            if item["classification"] == "INTERNAL_TRANSFER"
        ),
        2,
    )

    net = round(
        external_in + redemptions - external_out - applications,
        2,
    )

    return {
        "external_in": external_in,
        "external_out": external_out,
        "investment_applications": applications,
        "investment_redemptions": redemptions,
        "internal_transfers": internal,
        "net": net,
        "count": len(items),
        "items": items,
    }


def build_cash_flow_by_month(accounts: list, investments: list) -> dict[str, float]:
    result = build_monthly_cash_flow(accounts, investments)
    monthly: dict[str, float] = {}

    for item in result["items"]:
        key = item["month"]
        monthly[key] = monthly.get(key, 0.0) + float(item["impact"])

    return {
        key: round(value, 2)
        for key, value in monthly.items()
    }
