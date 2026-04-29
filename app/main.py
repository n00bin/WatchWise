from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.models.database import init_db
from app.routers import pages, api, auth

app = FastAPI(title="BingeWatcher")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(pages.router)
app.include_router(api.router)
app.include_router(auth.router)


@app.on_event("startup")
async def startup():
    init_db()
