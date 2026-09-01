from fastapi import FastAPI

from fastapi.middleware.cors import (
    CORSMiddleware,
)

from sqlalchemy import text

from app.database import (
    engine,
    Base,
)

from app import models

from app.routers import (
    auth,
    pluggy,
    finance,
    investments,
    monthly_breakdown,
    monthly_totals,
    investment_transactions,
    manual_commitments,
)


# =========================================================
# BANCO
# =========================================================

Base.metadata.create_all(
    bind=engine
)


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="Family Finance API"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],
)


# =========================================================
# ROTAS
# =========================================================

app.include_router(
    auth.router
)

app.include_router(
    pluggy.router
)

app.include_router(
    finance.router
)

app.include_router(
    investments.router
)

app.include_router(
    monthly_breakdown.router
)

app.include_router(
    monthly_totals.router
)

app.include_router(
    investment_transactions.router
)

app.include_router(
    manual_commitments.router
)


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():

    with engine.connect() as conn:
        conn.execute(
            text("SELECT 1")
        )

    return {
        "status": "ok",
        "database": "connected",
    }
