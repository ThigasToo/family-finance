from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from sqlalchemy.orm import Session

from app.database import get_db

from app.models import (
    User,
    ManualInvestment,
)

from app.security import get_current_user

from app.schemas import (
    ManualInvestmentCreate,
    ManualInvestmentUpdate,
    ManualInvestmentOut,
)


router = APIRouter(
    prefix="/investments",
    tags=["investments"],
)


# =========================================================
# LISTAR INVESTIMENTOS MANUAIS
# =========================================================


@router.get(
    "/manual",
    response_model=list[ManualInvestmentOut],
)
def list_manual_investments(
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    investments = (
        db.query(ManualInvestment)
        .filter(
            ManualInvestment.user_id
            == current_user.id
        )
        .order_by(
            ManualInvestment.created_at.desc()
        )
        .all()
    )

    return investments


# =========================================================
# BUSCAR UM INVESTIMENTO
# =========================================================


@router.get(
    "/manual/{investment_id}",
    response_model=ManualInvestmentOut,
)
def get_manual_investment(
    investment_id: int,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    investment = (
        db.query(ManualInvestment)
        .filter(
            ManualInvestment.id
            == investment_id,
            ManualInvestment.user_id
            == current_user.id,
        )
        .first()
    )

    if not investment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investimento não encontrado",
        )

    return investment


# =========================================================
# CRIAR INVESTIMENTO
# =========================================================


@router.post(
    "/manual",
    response_model=ManualInvestmentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_investment(
    data: ManualInvestmentCreate,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    investment = ManualInvestment(
        user_id=current_user.id,

        name=data.name.strip(),

        type=data.type
        .strip()
        .upper(),

        institution=data.institution.strip(),

        current_value=data.current_value,

        quantity=data.quantity,

        average_price=data.average_price,

        invested_value=data.invested_value,

        currency=data.currency
        .strip()
        .upper(),

        ticker=(
            data.ticker.strip().upper()
            if data.ticker
            else None
        ),

        source="MANUAL",
    )

    db.add(investment)

    db.commit()

    db.refresh(investment)

    return investment


# =========================================================
# ATUALIZAR INVESTIMENTO
# =========================================================


@router.patch(
    "/manual/{investment_id}",
    response_model=ManualInvestmentOut,
)
def update_manual_investment(
    investment_id: int,
    data: ManualInvestmentUpdate,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    investment = (
        db.query(ManualInvestment)
        .filter(
            ManualInvestment.id
            == investment_id,
            ManualInvestment.user_id
            == current_user.id,
        )
        .first()
    )

    if not investment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investimento não encontrado",
        )

    values = data.model_dump(
        exclude_unset=True
    )

    if "name" in values:
        values["name"] = (
            values["name"].strip()
        )

    if "type" in values:
        values["type"] = (
            values["type"]
            .strip()
            .upper()
        )

    if "institution" in values:
        values["institution"] = (
            values["institution"].strip()
        )

    if (
        "currency" in values
        and values["currency"] is not None
    ):
        values["currency"] = (
            values["currency"]
            .strip()
            .upper()
        )

    if (
        "ticker" in values
        and values["ticker"] is not None
    ):
        values["ticker"] = (
            values["ticker"]
            .strip()
            .upper()
        )

    for field, value in values.items():
        setattr(
            investment,
            field,
            value,
        )

    db.commit()

    db.refresh(investment)

    return investment


# =========================================================
# EXCLUIR INVESTIMENTO
# =========================================================


@router.delete(
    "/manual/{investment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_manual_investment(
    investment_id: int,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    investment = (
        db.query(ManualInvestment)
        .filter(
            ManualInvestment.id
            == investment_id,
            ManualInvestment.user_id
            == current_user.id,
        )
        .first()
    )

    if not investment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investimento não encontrado",
        )

    db.delete(investment)

    db.commit()

    return None