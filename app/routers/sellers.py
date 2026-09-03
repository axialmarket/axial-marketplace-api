"""Seller endpoints: CRUD, stats, recommendations, and the match sub-resource.

Mirror image of the buyers router -- creating/updating a seller reconciles its
matches; deleting it removes them.

Matches live *under* the seller (``/sellers/{id}/matches/...``); the lifecycle
transitions come from ``app.internal.match``. All state access goes through
``app.memory``.
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app import memory
from app.dependencies import get_seller_or_404
from app.internal.match import MatchStatus, advance, decline, pursue, reconcile_matches
from app.schemas import MatchAdvance, MatchOut, Recommendation, Stats
from app.internal.seller import (
    SellerCreate,
    SellerOut,
    SellerUpdate,
    new_seller,
    recommendations,
    stats,
)

router = APIRouter(prefix="/sellers", tags=["sellers"])


@router.post("", response_model=SellerOut, status_code=status.HTTP_201_CREATED)
def create_seller(payload: SellerCreate) -> Dict:
    """Register a seller, then generate matches against compatible buyers."""
    seller = memory.add_seller(new_seller(payload))
    reconcile_matches(seller)
    return seller


@router.get("", response_model=List[SellerOut])
def list_sellers(
    status_filter: Optional[str] = Query(None, alias="status"),
    geography: Optional[str] = None,
    industry: Optional[int] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> List[Dict]:
    """List sellers with optional filters and pagination."""
    sellers = memory.all_sellers()
    if status_filter is not None:
        sellers = [s for s in sellers if s["status"] == status_filter]
    if geography is not None:
        sellers = [s for s in sellers if s["geography"] == geography]
    if industry is not None:
        sellers = [s for s in sellers if industry in s["industries"]]
    return sellers[offset : offset + limit]


@router.get("/stats", response_model=Stats)
def seller_stats() -> Dict:
    """Low/high asking price across all sellers (``low``/``high`` None if empty)."""
    return stats(memory.all_sellers())


@router.get("/{seller_id}", response_model=SellerOut)
def get_seller(seller: Dict = Depends(get_seller_or_404)) -> Dict:
    return seller


@router.put("/{seller_id}", response_model=SellerOut)
def update_seller(payload: SellerUpdate, seller: Dict = Depends(get_seller_or_404)) -> Dict:
    """Apply a partial update, then reconcile this seller's matches.

    See ``update_buyer`` -- ``reconcile_matches`` creates, drops, or leaves this
    seller's intro matches in a single pass.
    """
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates:
        updates["status"] = updates["status"].value
    seller.update(updates)
    reconcile_matches(seller)
    return seller


@router.delete("/{seller_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_seller(seller: Dict = Depends(get_seller_or_404)) -> None:
    """Hard-delete the seller and every match that references it."""
    for match in memory.all_matches():
        if match["seller"] == seller["id"]:
            memory.remove_match(match)
    memory.remove_seller(seller)


@router.get("/{seller_id}/recommendations", response_model=List[Recommendation])
def seller_recommendations(seller: Dict = Depends(get_seller_or_404)) -> List[Dict]:
    """Live list of compatible active buyers, ranked by score (highest first)."""
    return recommendations(seller, memory.all_buyers())


# --------------------------------------------------------------------------- #
# Matches sub-resource: /sellers/{seller_id}/matches/...
# --------------------------------------------------------------------------- #
@router.get("/{seller_id}/matches", response_model=List[MatchOut])
def seller_matches(
    seller: Dict = Depends(get_seller_or_404),
    status_filter: Optional[MatchStatus] = Query(None, alias="status"),
) -> List[Dict]:
    """All persisted matches for this seller, optionally filtered by status."""
    matches = [m for m in memory.all_matches() if m["seller"] == seller["id"]]
    if status_filter is not None:
        matches = [m for m in matches if m["status"] == status_filter.value]
    return matches


@router.get("/{seller_id}/matches/{match_id}", response_model=MatchOut)
def seller_match(
    match_id: int = Path(..., ge=1), seller: Dict = Depends(get_seller_or_404)
) -> Dict:
    match = memory.get_match(match_id)
    if match is None or match["seller"] != seller["id"]:
        raise HTTPException(status_code=404, detail=f"match {match_id} not found")
    return match


@router.post("/{seller_id}/matches/{match_id}/pursue", response_model=MatchOut)
def pursue_seller_match(
    match_id: int = Path(..., ge=1), seller: Dict = Depends(get_seller_or_404)
) -> Dict:
    """Pursue this match: intro -> pursued."""
    match = memory.get_match(match_id)
    if match is None or match["seller"] != seller["id"]:
        raise HTTPException(status_code=404, detail=f"match {match_id} not found")
    pursue(match)
    return match


@router.post("/{seller_id}/matches/{match_id}/decline", response_model=MatchOut)
def decline_seller_match(
    match_id: int = Path(..., ge=1), seller: Dict = Depends(get_seller_or_404)
) -> Dict:
    """Decline this match from any live stage -> declined."""
    match = memory.get_match(match_id)
    if match is None or match["seller"] != seller["id"]:
        raise HTTPException(status_code=404, detail=f"match {match_id} not found")
    decline(match)
    return match


@router.patch("/{seller_id}/matches/{match_id}", response_model=MatchOut)
def advance_seller_match(
    payload: MatchAdvance,
    match_id: int = Path(..., ge=1),
    seller: Dict = Depends(get_seller_or_404),
) -> Dict:
    """Advance this pursued match forward through the deal pipeline."""
    match = memory.get_match(match_id)
    if match is None or match["seller"] != seller["id"]:
        raise HTTPException(status_code=404, detail=f"match {match_id} not found")
    advance(match, payload.status)
    return match
