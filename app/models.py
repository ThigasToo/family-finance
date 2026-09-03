from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    ForeignKey,
    JSON,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )

    pluggy_items = relationship(
        "PluggyItem",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    snapshot = relationship(
        "FinancialSnapshot",
        back_populates="owner",
        uselist=False,
        cascade="all, delete-orphan",
    )
    monthly_snapshots = relationship(
        "MonthlyFinancialSnapshot",
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    manual_investments = relationship(
        "ManualInvestment",
        back_populates="owner",
        cascade="all, delete-orphan",
    )


class PluggyItem(Base):
    __tablename__ = "pluggy_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_id = Column(String, unique=True, nullable=False)
    institution_name = Column(String, nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )
    owner = relationship("User", back_populates="pluggy_items")


class FinancialSnapshot(Base):
    __tablename__ = "financial_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )
    payload = Column(JSON, nullable=False, default=dict)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
    )
    owner = relationship("User", back_populates="snapshot")


class MonthlyFinancialSnapshot(Base):
    """Resposta mensal pré-calculada derivada do snapshot financeiro."""

    __tablename__ = "monthly_financial_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "month",
            name="uq_monthly_financial_snapshot_user_month",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    month = Column(String(7), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    source_updated_at = Column(DateTime, nullable=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    owner = relationship("User", back_populates="monthly_snapshots")


class MonthlyManualCommitment(Base):
    """Valor informado manualmente para comprometer o caixa de um mês."""

    __tablename__ = "monthly_manual_commitments"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "month",
            name="uq_monthly_manual_commitment_user_month",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    month = Column(String(7), nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False, default=0)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class MonthlyCardPeriod(Base):
    """Intervalo de compras de cartão escolhido pelo usuário para um mês."""

    __tablename__ = "monthly_card_periods"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "month",
            name="uq_monthly_card_period_user_month",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    month = Column(String(7), nullable=False, index=True)
    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ManualInvestment(Base):
    __tablename__ = "manual_investments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)
    institution = Column(String, nullable=False)
    current_value = Column(Numeric(18, 2), nullable=False, default=0)
    quantity = Column(Numeric(30, 12), nullable=True)
    average_price = Column(Numeric(18, 8), nullable=True)
    invested_value = Column(Numeric(18, 2), nullable=True)
    currency = Column(String, nullable=False, default="BRL")
    ticker = Column(String, nullable=True)
    source = Column(String, nullable=False, default="MANUAL")
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    owner = relationship("User", back_populates="manual_investments")
