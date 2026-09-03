"""Buyer endpoints: CRUD, stats, recommendations, and the match sub-resource.

Creating or updating a buyer reconciles its matches (see
``app.internal.match.reconcile_matches``); deleting it removes them.

Matches live *under* the buyer (``/buyers/{id}/matches/...``); the lifecycle
transitions come from ``app.internal.match``. All state access goes through
``app.memory``.
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app import memory
from app.internal.buyer import (
    BuyerCreate,
    BuyerOut,
    BuyerUpdate,
    new_buyer,
    recommendations,
    stats,
)
from app.dependencies import get_buyer_or_404
from app.internal.match import MatchStatus, advance, decline, pursue, reconcile_matches
from app.schemas import MatchAdvance, MatchOut, Recommendation, Stats

router = APIRouter(prefix="/buyers", tags=["buyers"])


@router.post("", response_model=BuyerOut, status_code=status.HTTP_201_CREATED)
def create_buyer(payload: BuyerCreate) -> Dict:
    """Register a buyer, then generate matches against compatible sellers."""
    buyer = memory.add_buyer(new_buyer(payload))
    reconcile_matches(buyer)
    return buyer


@router.get("", response_model=List[BuyerOut])
def list_buyers(
    status_filter: Optional[str] = Query(None, alias="status"),
    geography: Optional[str] = None,
    industry: Optional[int] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[Dict]:
    """List buyers with optional filters and pagination."""
    buyers = memory.all_buyers()
    if status_filter is not None:
        buyers = [b for b in buyers if b["status"] == status_filter]
    if geography is not None:
        buyers = [b for b in buyers if geography in b["geographies"]]
    if industry is not None:
        buyers = [b for b in buyers if industry in b["industries"]]
    return buyers[offset : offset + limit]


@router.get("/stats", response_model=Stats)
def buyer_stats() -> Dict:
    """Low/high price limits across all buyers (``low``/``high`` are None if empty)."""
    return stats(memory.all_buyers())


@router.get("/{buyer_id}", response_model=BuyerOut)
def get_buyer(buyer: Dict = Depends(get_buyer_or_404)) -> Dict:
    return buyer


@router.put("/{buyer_id}", response_model=BuyerOut)
def update_buyer(payload: BuyerUpdate, buyer: Dict = Depends(get_buyer_or_404)) -> Dict:
    """Apply a partial update, then reconcile this buyer's matches.

    ``reconcile_matches`` handles every case in one pass: it creates matches for
    newly-compatible sellers, drops intro matches that no longer fit (including
    when the buyer goes inactive), and leaves progressed deals alone.
    """
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates:
        updates["status"] = updates["status"].value
    buyer.update(updates)
    reconcile_matches(buyer)
    return buyer


@router.delete("/{buyer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_buyer(buyer: Dict = Depends(get_buyer_or_404)) -> None:
    """Hard-delete the buyer and every match that references it."""
    for match in memory.all_matches():
        if match["buyer"] == buyer["id"]:
            memory.remove_match(match)
    memory.remove_buyer(buyer)


@router.get("/{buyer_id}/recommendations", response_model=List[Recommendation])
def buyer_recommendations(buyer: Dict = Depends(get_buyer_or_404)) -> List[Dict]:
    """Live list of compatible active sellers, ranked by score (highest first)."""
    return recommendations(buyer, memory.all_sellers())


# --------------------------------------------------------------------------- #
# Matches sub-resource: /buyers/{buyer_id}/matches/...
# --------------------------------------------------------------------------- #
@router.get("/{buyer_id}/matches", response_model=List[MatchOut])
def buyer_matches(
    buyer: Dict = Depends(get_buyer_or_404),
    status_filter: Optional[MatchStatus] = Query(None, alias="status"),
) -> List[Dict]:
    """All persisted matches for this buyer, optionally filtered by status."""
    matches = [m for m in memory.all_matches() if m["buyer"] == buyer["id"]]
    if status_filter is not None:
        matches = [m for m in matches if m["status"] == status_filter.value]
    return matches


@router.get("/{buyer_id}/matches/{match_id}", response_model=MatchOut)
def buyer_match(
    match_id: int = Path(..., ge=1), buyer: Dict = Depends(get_buyer_or_404)
) -> Dict:
    match = memory.get_match(match_id)
    if match is None or match["buyer"] != buyer["id"]:
        raise HTTPException(status_code=404, detail=f"match {match_id} not found")
    return match


@router.post("/{buyer_id}/matches/{match_id}/pursue", response_model=MatchOut)
def pursue_buyer_match(
    match_id: int = Path(..., ge=1), buyer: Dict = Depends(get_buyer_or_404)
) -> Dict:
    """Pursue this match: intro -> pursued."""
    match = memory.get_match(match_id)
    if match is None or match["buyer"] != buyer["id"]:
        raise HTTPException(status_code=404, detail=f"match {match_id} not found")
    pursue(match)
    return match


@router.post("/{buyer_id}/matches/{match_id}/decline", response_model=MatchOut)
def decline_buyer_match(
    match_id: int = Path(..., ge=1), buyer: Dict = Depends(get_buyer_or_404)
) -> Dict:
    """Decline this match from any live stage -> declined."""
    match = memory.get_match(match_id)
    if match is None or match["buyer"] != buyer["id"]:
        raise HTTPException(status_code=404, detail=f"match {match_id} not found")
    decline(match)
    return match


@router.patch("/{buyer_id}/matches/{match_id}", response_model=MatchOut)
def advance_buyer_match(
    payload: MatchAdvance,
    match_id: int = Path(..., ge=1),
    buyer: Dict = Depends(get_buyer_or_404),
) -> Dict:
    """Advance this pursued match forward through the deal pipeline."""
    match = memory.get_match(match_id)
    if match is None or match["buyer"] != buyer["id"]:
        raise HTTPException(status_code=404, detail=f"match {match_id} not found")
    advance(match, payload.status)
    return match
