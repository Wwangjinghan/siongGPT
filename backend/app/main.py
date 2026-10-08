from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.auth import router as auth_router
from app.api.v1.ingestion import router as ingestion_router
from app.api.v1.search import router as search_router
from app.api.v1.sources import router as sources_router
from app.core.database import engine


app = FastAPI(
    title="Siong GPT API",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(
    auth_router,
    prefix="/api/v1",
)
app.include_router(sources_router, prefix="/api/v1")
app.include_router(ingestion_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "siong-gpt-backend",
    }


@app.get("/health/db")
def database_health_check():
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT current_database(), current_user")
        ).one()

    return {
        "status": "ok",
        "database": result[0],
        "user": result[1],
    }
