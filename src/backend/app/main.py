from fastapi import FastAPI
from app.database import engine
from app import models

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="HireWise",
    description="A Recruitment Software",
    version="1.0.0"
)

@app.get("/")
def read_root():
    return {"message": "Hello World!"}