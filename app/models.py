from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    JSON,
    Numeric,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    name = Column(
        String,
        nullable=False,
    )

    email = Column(
        String,
        unique=True,
        index=True,
        nullable=False,
    )

    hashed_password = Column(
        String,
        nullable=False,
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(
            timezone.utc
        ),
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

    manual_investments = relationship(
        "ManualInvestment",
        back_populates="owner",
        cascade="all, delete-orphan",
    )


class PluggyItem(Base):
    """
    Cada linha representa uma conexão
    bancária do usuário com a Pluggy.
    """

    __tablename__ = "pluggy_items"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    item_id = Column(
        String,
        unique=True,
        nullable=False,
    )

    institution_name = Column(
        String,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(
            timezone.utc
        ),
    )

    owner = relationship(
        "User",
        back_populates="pluggy_items",
    )


class FinancialSnapshot(Base):
    """
    Cache dos dados vindos das conexões
    financeiras.

    Investimentos manuais NÃO são
    persistidos dentro deste snapshot.
    """

    __tablename__ = "financial_snapshots"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False,
    )

    payload = Column(
        JSON,
        nullable=False,
        default=dict,
    )

    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(
            timezone.utc
        ),
    )

    owner = relationship(
        "User",
        back_populates="snapshot",
    )


class ManualInvestment(Base):
    """
    Investimento cadastrado manualmente
    pelo usuário.

    Os campos adicionais já deixam a
    estrutura preparada para cálculos
    futuros de rentabilidade.
    """

    __tablename__ = "manual_investments"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # Ex.: Bitcoin, IVVB11, Ethereum
    name = Column(
        String,
        nullable=False,
    )

    # Ex.: CRYPTO, ETF, STOCK, FUND
    type = Column(
        String,
        nullable=False,
    )

    # Ex.: Binance, Mercado Bitcoin, Rico
    institution = Column(
        String,
        nullable=False,
    )

    # Valor de mercado informado manualmente
    current_value = Column(
        Numeric(18, 2),
        nullable=False,
        default=0,
    )

    # =====================================================
    # CAMPOS PREPARADOS PARA USO FUTURO
    # =====================================================

    # Ex.: 0.01234567 BTC ou 20 cotas
    quantity = Column(
        Numeric(30, 12),
        nullable=True,
    )

    # Preço médio por unidade
    average_price = Column(
        Numeric(18, 8),
        nullable=True,
    )

    # Quanto foi efetivamente aportado
    invested_value = Column(
        Numeric(18, 2),
        nullable=True,
    )

    # BRL, USD etc.
    currency = Column(
        String,
        nullable=False,
        default="BRL",
    )

    # BTC, IVVB11, ETH etc.
    ticker = Column(
        String,
        nullable=True,
    )

    source = Column(
        String,
        nullable=False,
        default="MANUAL",
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(
            timezone.utc
        ),
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(
            timezone.utc
        ),
        onupdate=lambda: datetime.now(
            timezone.utc
        ),
        nullable=False,
    )

    owner = relationship(
        "User",
        back_populates="manual_investments",
    )