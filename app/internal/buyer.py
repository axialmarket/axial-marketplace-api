"""Buyer: schema, structure, and buyer-specific helpers.

Everything that defines a buyer lives here: its API schema (the Pydantic
request/response models), how a stored buyer dict is built (:func:`new_buyer`),
and the read helpers the router exposes (:func:`stats`, :func:`recommendations`).

A buyer is stored as a plain dict; ``id`` and ``type`` are stamped on by
``app.memory.add_buyer``. Compatibility and scoring live in
``app.internal.match``.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from app.internal.match import is_compatible, match_details
from app.schemas import EntityStatus


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
class BuyerCreate(BaseModel):
    name: str = Field(..., min_length=1)
    lower_limit: int = Field(..., ge=0, description="Lowest price the buyer will pay.")
    upper_limit: int = Field(..., ge=0, description="Highest price the buyer will pay.")
    geographies: List[str] = Field(..., min_length=1, description="e.g. ['NY', 'TX'].")
    industries: List[int] = Field(..., min_length=1, description="Industry node ids.")

    @model_validator(mode="after")
    def _check_limits(self) -> "BuyerCreate":
        if self.lower_limit > self.upper_limit:
            raise ValueError("lower_limit must be <= upper_limit")
        return self


class BuyerUpdate(BaseModel):
    """Partial update. Any omitted field is left unchanged."""

    name: Optional[str] = Field(None, min_length=1)
    lower_limit: Optional[int] = Field(None, ge=0)
    upper_limit: Optional[int] = Field(None, ge=0)
    geographies: Optional[List[str]] = Field(None, min_length=1)
    industries: Optional[List[int]] = Field(None, min_length=1)
    status: Optional[EntityStatus] = None


class BuyerOut(BaseModel):
    id: int
    name: str
    lower_limit: int
    upper_limit: int
    geographies: List[str]
    industries: List[int]
    status: EntityStatus


# --------------------------------------------------------------------------- #
# Structure
# --------------------------------------------------------------------------- #
def new_buyer(payload: BuyerCreate) -> Dict:
    """Build a storable buyer dict (active) from a validated create payload.

    ``id``/``type`` are added by ``app.memory.add_buyer`` when it is saved.
    """
    return {"status": EntityStatus.ACTIVE.value, **payload.model_dump()}


# --------------------------------------------------------------------------- #
# Read helpers
# --------------------------------------------------------------------------- #
def stats(buyers: List[Dict]) -> Dict:
    """Low/high price limits across ``buyers`` (``None``/``None``/0 when empty)."""
    if not buyers:
        return {"low": None, "high": None, "count": 0}
    return {
        "low": min(b["lower_limit"] for b in buyers),
        "high": max(b["upper_limit"] for b in buyers),
        "count": len(buyers),
    }


def recommendations(buyer: Dict, sellers: List[Dict]) -> List[Dict]:
    """Compatible active sellers for ``buyer``, ranked by score (highest first)."""
    recs = [
        {"id": s["id"], "name": s["name"], **match_details(buyer, s)}
        for s in sellers
        if is_compatible(buyer, s)
    ]
    recs.sort(key=lambda r: r["score"], reverse=True)
    return recs
