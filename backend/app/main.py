from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import runs, stream
from app.routers.runs import stats_router

# Load .env from project root (parent of backend/)
_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(_backend_dir.parent / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="SoloCarta", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(runs.router)
app.include_router(stream.router)
app.include_router(stats_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
