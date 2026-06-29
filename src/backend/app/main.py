from fastapi import FastAPI
from app.database import engine, SessionLocal
from app import models
from app.core.bootstrap import ensure_default_admin
from app.routers import auth, users

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="HireWise",
    description="A Recruitment Software",
    version="1.0.0"
)

app.include_router(auth.router)
app.include_router(users.router)


@app.on_event("startup")
def seed_default_admin():
    db = SessionLocal()
    try:
        ensure_default_admin(db)
    finally:
        db.close()

@app.get("/")
def read_root():
    return {"message": "Hello World!"}