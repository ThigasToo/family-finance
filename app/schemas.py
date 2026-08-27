from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
)


# =========================================================
# USUÁRIOS / AUTENTICAÇÃO
# =========================================================


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# =========================================================
# FINANCEIRO
# =========================================================


class FinanceSummaryOut(BaseModel):
    payload: dict[str, Any]
    updated_at: datetime | None


class FinanceRefreshOut(BaseModel):
    status: str
    updated_at: datetime


# =========================================================
# INVESTIMENTOS MANUAIS
# =========================================================


class ManualInvestmentCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=120,
    )

    type: str = Field(
        min_length=1,
        max_length=50,
    )

    institution: str = Field(
        min_length=1,
        max_length=120,
    )

    current_value: Decimal = Field(
        ge=0,
    )

    # ---------------------------------------------
    # Campos opcionais para funcionalidades futuras
    # ---------------------------------------------

    quantity: Decimal | None = Field(
        default=None,
        ge=0,
    )

    average_price: Decimal | None = Field(
        default=None,
        ge=0,
    )

    invested_value: Decimal | None = Field(
        default=None,
        ge=0,
    )

    currency: str = Field(
        default="BRL",
        min_length=3,
        max_length=10,
    )

    ticker: str | None = Field(
        default=None,
        max_length=30,
    )


class ManualInvestmentUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
    )

    type: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    institution: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
    )

    current_value: Decimal | None = Field(
        default=None,
        ge=0,
    )

    quantity: Decimal | None = Field(
        default=None,
        ge=0,
    )

    average_price: Decimal | None = Field(
        default=None,
        ge=0,
    )

    invested_value: Decimal | None = Field(
        default=None,
        ge=0,
    )

    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=10,
    )

    ticker: str | None = Field(
        default=None,
        max_length=30,
    )


class ManualInvestmentOut(BaseModel):
    id: int

    name: str
    type: str
    institution: str

    current_value: Decimal

    quantity: Decimal | None
    average_price: Decimal | None
    invested_value: Decimal | None

    currency: str
    ticker: str | None

    source: str

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True