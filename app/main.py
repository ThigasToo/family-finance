from fastapi import FastAPI
from sqlalchemy import text
from app.database import engine, Base
from app import models  # garante que os modelos são registrados no Base
from app.routers import auth
from app.routers import auth, pluggy
from app.routers import auth, pluggy, finance

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Family Finance API")

@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


app.include_router(auth.router)
app.include_router(pluggy.router)
app.include_router(finance.router)