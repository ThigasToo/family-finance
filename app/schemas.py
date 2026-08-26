from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Any


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

class FinanceSummaryOut(BaseModel):
    payload: dict[str, Any]
    updated_at: datetime | None


class FinanceRefreshOut(BaseModel):
    status: str
    updated_at: datetime