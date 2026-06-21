from fastapi import FastAPI

app = FastAPI(
    title="HiseWise",
    description="A Recruitment Software",
    version="1.0.0"
)

@app.get("/")
def read_root():
    return {"message": "Hello World!"}