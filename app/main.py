from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.database import engine, Base
from app import models
from app.routers import auth, pluggy, finance

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Family Finance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # em produção, restrinja para o domínio real do app
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(pluggy.router)
app.include_router(finance.router)


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}