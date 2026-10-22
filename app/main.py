from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.auth import router as auth_router
from app.core.config import settings
from app.database import get_db
from app.api.repositories import router as repositories_router

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
)

app.include_router(auth_router)

app.include_router(repositories_router, prefix="/api")

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