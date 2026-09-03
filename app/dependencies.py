"""Shared FastAPI dependencies -- store lookups that 404 when missing."""
from typing import Dict

from fastapi import HTTPException, Path

from app import memory


def get_buyer_or_404(buyer_id: int = Path(..., ge=1)) -> Dict:
    buyer = memory.get_buyer(buyer_id)
    if buyer is None:
        raise HTTPException(status_code=404, detail=f"buyer {buyer_id} not found")
    return buyer


def get_seller_or_404(seller_id: int = Path(..., ge=1)) -> Dict:
    seller = memory.get_seller(seller_id)
    if seller is None:
        raise HTTPException(status_code=404, detail=f"seller {seller_id} not found")
    return seller


def get_match_or_404(match_id: int = Path(..., ge=1)) -> Dict:
    match = memory.get_match(match_id)
    if match is None:
        raise HTTPException(status_code=404, detail=f"match {match_id} not found")
    return match
