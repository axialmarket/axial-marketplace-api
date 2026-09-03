"""Shared, cross-entity Pydantic models.

Buyer- and seller-specific schemas live with their domain logic in
``app.internal.buyer`` and ``app.internal.seller``. What remains here is the
handful of models used by more than one entity (``EntityStatus``, ``Stats``,
``Recommendation``) plus the match request/response models.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from app.internal.match import MatchStatus


class EntityStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


# --------------------------------------------------------------------------- #
# Matches
# --------------------------------------------------------------------------- #
class MatchOut(BaseModel):
    id: int
    buyer: int  # buyer id
    seller: int  # seller id
    status: MatchStatus
    pursued: bool
    score: float
    matched_geographies: List[str]
    matched_industries: List[int]
    created_at: str
    updated_at: str


class MatchAdvance(BaseModel):
    """Body for PATCH .../matches/{id} -- move a pursued match to a later stage."""

    status: MatchStatus


# --------------------------------------------------------------------------- #
# Stats & recommendations (shared by buyers and sellers)
# --------------------------------------------------------------------------- #
class Stats(BaseModel):
    low: Optional[int] = None
    high: Optional[int] = None
    count: int


class Recommendation(BaseModel):
    id: int
    name: str
    score: float
    matched_geographies: List[str]
    matched_industries: List[int]
