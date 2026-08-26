from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    pluggy_items = relationship("PluggyItem", back_populates="owner", cascade="all, delete-orphan")
    snapshot = relationship("FinancialSnapshot", back_populates="owner", uselist=False, cascade="all, delete-orphan")


class PluggyItem(Base):
    """Cada linha = uma conexão bancária (item) de um membro da família."""
    __tablename__ = "pluggy_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_id = Column(String, unique=True, nullable=False)       # itemId da Pluggy
    institution_name = Column(String, nullable=True)             # ex: "Nubank"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="pluggy_items")


class FinancialSnapshot(Base):
    """Cache dos dados financeiros de um usuário — o app sempre lê daqui."""
    __tablename__ = "financial_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)         # contas, transações, investimentos processados
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="snapshot")