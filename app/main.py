"""Axial marketplace API.

A small FastAPI service that models a buyer/seller marketplace on top of an
industry taxonomy. Buyers and sellers are matched into ``Match`` objects that
each follow a deal-pipeline lifecycle (intro -> pursued -> ... -> closed, or
declined). Everything is stored in process memory -- see ``app.memory``.

The store is filled on start-up from the hard-coded data in ``app.seed_data``,
so the API comes up with a marketplace already in motion. Nothing is generated
at boot -- the literals are copied in as they are.

Loading is bound to the application lifespan, so it runs for a real server but
not for a bare ``TestClient(app)`` -- the test suite builds its own fixtures and
expects to start from empty.

Run locally::

    uvicorn app.main:app --reload

Then open http://127.0.0.1:8000/docs for interactive API docs.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import memory, seed
from app.routers import buyers, sellers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Copy the hard-coded seed data in before the first request is served."""
    logger.info(seed.summary(seed.load_seed()))
    yield
    memory.reset()


app = FastAPI(
    title="Axial Marketplace API",
    version="1.0.0",
    description="Buyer/seller marketplace with industry-tree matching and a match lifecycle.",
    lifespan=lifespan,
)

app.include_router(buyers.router)
app.include_router(sellers.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}
