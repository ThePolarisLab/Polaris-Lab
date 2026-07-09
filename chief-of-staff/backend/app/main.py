from fastapi import FastAPI

from app.database.database import Base, engine
from app.models.company import Company

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Polaris Chief of Staff")


@app.get("/")
def root():
    return {
        "service": "Polaris Chief of Staff API",
        "version": "0.2",
        "database": "Connected"
    }