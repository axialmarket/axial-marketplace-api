"""Seller: schema, structure, and seller-specific helpers.

Mirror of ``app.internal.buyer``: the Pydantic request/response models, the stored-dict
constructor (:func:`new_seller`), and the read helpers the router exposes
(:func:`stats`, :func:`recommendations`).

A seller is stored as a plain dict; ``id`` and ``type`` are stamped on by
``app.memory.add_seller``. Compatibility and scoring live in
``app.internal.match``.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.internal.match import is_compatible, match_details
from app.schemas import EntityStatus


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
class SellerCreate(BaseModel):
    name: str = Field(..., min_length=1)
    selling_price: int = Field(..., ge=0, description="Asking price.")
    geography: str = Field(..., min_length=1, description="Single US state, e.g. 'NY'.")
    industries: List[int] = Field(..., min_length=1, description="Industry node ids.")


class SellerUpdate(BaseModel):
    """Partial update. Any omitted field is left unchanged."""

    name: Optional[str] = Field(None, min_length=1)
    selling_price: Optional[int] = Field(None, ge=0)
    geography: Optional[str] = Field(None, min_length=1)
    industries: Optional[List[int]] = Field(None, min_length=1)
    status: Optional[EntityStatus] = None


class SellerOut(BaseModel):
    id: int
    name: str
    selling_price: int
    geography: str
    industries: List[int]
    status: EntityStatus


# --------------------------------------------------------------------------- #
# Structure
# --------------------------------------------------------------------------- #
def new_seller(payload: SellerCreate) -> Dict:
    """Build a storable seller dict (active) from a validated create payload.

    ``id``/``type`` are added by ``app.memory.add_seller`` when it is saved.
    """
    return {"status": EntityStatus.ACTIVE.value, **payload.model_dump()}


# --------------------------------------------------------------------------- #
# Read helpers
# --------------------------------------------------------------------------- #
def stats(sellers: List[Dict]) -> Dict:
    """Low/high asking price across ``sellers`` (``None``/``None``/0 when empty)."""
    if not sellers:
        return {"low": None, "high": None, "count": 0}
    return {
        "low": min(s["selling_price"] for s in sellers),
        "high": max(s["selling_price"] for s in sellers),
        "count": len(sellers),
    }


def recommendations(seller: Dict, buyers: List[Dict]) -> List[Dict]:
    """Compatible active buyers for ``seller``, ranked by score (highest first)."""
    recs = [
        {"id": b["id"], "name": b["name"], **match_details(b, seller)}
        for b in buyers
        if is_compatible(b, seller)
    ]
    recs.sort(key=lambda r: r["score"], reverse=True)
    return recs
