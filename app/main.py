from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.auth import router as auth_router
from app.api.repositories import router as repositories_router
from app.api.retrieval import router as retrieval_router
from app.core.config import settings
from app.database import get_db

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
)

# ---------------------------------------------------------------------------
# CORS – allow the Vite dev server and any production origin you deploy to.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://127.0.0.1:5173",
        "http://localhost:4173",   # Vite preview
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

app.include_router(repositories_router, prefix="/api")
app.include_router(retrieval_router, prefix="/api")

@app.get("/")
def root():
    return {"message": "RepoPilot AI", "docs": "/docs"}


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )