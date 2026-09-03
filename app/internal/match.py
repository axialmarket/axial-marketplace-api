"""Match: compatibility, scoring, structure, and lifecycle -- everything that
defines a match between a buyer and a seller.

The module has three parts:

**Compatibility & scoring** (pure functions over the plain buyer/seller dicts):
whether a buyer and seller match at all, and how strong that match is.
Compatibility follows the original take-home rules and is **symmetric**:

* **geography** -- the seller's single geography is one of the buyer's geographies.
* **price band** -- ``buyer.lower_limit <= seller.selling_price <= buyer.upper_limit``.
* **industry** -- at least one seller industry equals, or is a descendant of, at
  least one buyer industry. (Equivalently: a buyer industry is an ancestor of a
  seller industry -- the two phrasings are the same relation.)

**Match object & lifecycle**: a match links a buyer and seller and moves through
a deal pipeline::

    intro -> pursued -> nda_signed -> cim_exchanged -> loi_issued -> closed

with ``declined`` as a terminal off-ramp reachable from any live stage.
:func:`new_match` builds the dict; :func:`pursue`, :func:`decline` and
:func:`advance` validate and then apply a status change. Transition rules:

* Every match starts in ``intro``.
* :func:`pursue`  -- only from ``intro``; sets the ``pursued`` flag permanently.
* :func:`decline` -- from any non-terminal stage -> ``declined``.
* :func:`advance` -- allowed **only once a match has been pursued**; may move
  forward to any later deal stage (skips allowed) but never backward, and never
  back into ``intro``/``pursued``. Allowed targets are derived purely from
  position in :data:`PIPELINE`.

Invalid transitions raise :class:`TransitionError`, an ``HTTPException`` that
surfaces directly as a ``409 Conflict``.

**Matchmaking**: :func:`reconcile_matches` brings a buyer's or seller's ``intro``
matches in line with reality against the ``app.memory`` store.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Tuple

from fastapi import HTTPException

from app import memory
from app.internal.industries import get_industry_node


# --------------------------------------------------------------------------- #
# Compatibility & scoring (pure)
# --------------------------------------------------------------------------- #
def matched_geographies(buyer: Dict, seller: Dict) -> List[str]:
    """Geographies the pair share (0 or 1 -- a seller has a single geography)."""
    if seller["geography"] in buyer["geographies"]:
        return [seller["geography"]]
    return []


def matched_industries(buyer: Dict, seller: Dict) -> List[int]:
    """Seller industries that equal or descend from a buyer industry.

    Sorted for deterministic output.
    """
    matches = set()
    for buyer_industry in buyer["industries"]:
        node = get_industry_node(buyer_industry)
        if node is None:
            continue
        for seller_industry in seller["industries"]:
            if seller_industry in node.children_ids:
                matches.add(seller_industry)
    return sorted(matches)


def _price_fit(buyer: Dict, seller: Dict) -> float:
    """How centered the price is within the buyer's band, in ``[0, 1]``.

    1.0 means the price sits exactly at the midpoint of the band; the value
    falls toward 0.0 as the price approaches either limit. A zero-width band
    (lower == upper) is treated as a perfect fit.
    """
    low, high, price = buyer["lower_limit"], buyer["upper_limit"], seller["selling_price"]
    span = high - low
    if span <= 0:
        return 1.0
    midpoint = (high + low) / 2
    return 1.0 - abs(price - midpoint) / (span / 2)


def is_compatible(buyer: Dict, seller: Dict) -> bool:
    """True if the buyer and seller satisfy geography, price and industry rules.

    Inactive buyers/sellers never match.
    """
    if buyer.get("status") != "active" or seller.get("status") != "active":
        return False
    if seller["geography"] not in buyer["geographies"]:
        return False
    if not (buyer["lower_limit"] <= seller["selling_price"] <= buyer["upper_limit"]):
        return False
    return bool(matched_industries(buyer, seller))


def score_match(buyer: Dict, seller: Dict) -> float:
    """Score a compatible pair. Higher is a stronger match.

    Weighted so that industry overlap dominates (each shared industry is worth
    10 points) and price-fit acts as a tie-breaker (0..1). Rounded to keep
    responses and test assertions tidy.
    """
    industry_points = len(matched_industries(buyer, seller)) * 10.0
    return round(industry_points + _price_fit(buyer, seller), 4)


def match_details(buyer: Dict, seller: Dict) -> Dict:
    """Snapshot of why a pair matched -- stored on the match at creation time."""
    return {
        "score": score_match(buyer, seller),
        "matched_geographies": matched_geographies(buyer, seller),
        "matched_industries": matched_industries(buyer, seller),
    }


# --------------------------------------------------------------------------- #
# Lifecycle state machine
# --------------------------------------------------------------------------- #
class MatchStatus(str, Enum):
    INTRO = "intro"
    PURSUED = "pursued"
    NDA_SIGNED = "nda_signed"
    CIM_EXCHANGED = "cim_exchanged"
    LOI_ISSUED = "loi_issued"
    CLOSED = "closed"
    DECLINED = "declined"


# Forward pipeline order. ``declined`` is intentionally absent -- it is terminal
# and only reachable via :func:`decline`.
PIPELINE: List[MatchStatus] = [
    MatchStatus.INTRO,
    MatchStatus.PURSUED,
    MatchStatus.NDA_SIGNED,
    MatchStatus.CIM_EXCHANGED,
    MatchStatus.LOI_ISSUED,
    MatchStatus.CLOSED,
]

_RANK = {status: i for i, status in enumerate(PIPELINE)}

# First deal stage :func:`advance` may set: everything after ``pursued`` in the
# pipeline (nda_signed, cim_exchanged, loi_issued, closed).
_MIN_ADVANCE_RANK = _RANK[MatchStatus.PURSUED] + 1

TERMINAL = {MatchStatus.CLOSED, MatchStatus.DECLINED}


class TransitionError(HTTPException):
    """A disallowed lifecycle transition.

    Subclasses :class:`fastapi.HTTPException` so that raising it inside a request
    bubbles straight up as a ``409 Conflict`` -- no router-level try/except.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=409, detail=detail)


# --------------------------------------------------------------------------- #
# Structure
# --------------------------------------------------------------------------- #
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_match(buyer: Dict, seller: Dict) -> Dict:
    """Build a fresh ``intro`` match for a compatible buyer/seller pair.

    The ``buyer``/``seller`` fields hold the parties' ids. The returned dict has
    no ``type``/``id`` yet -- the store stamps those when the match is saved
    (see ``app.memory.add_match``).

    The score and matched geographies/industries are snapshotted at creation
    time so the match's lifecycle is independent of later edits to either party.
    """
    now = _now()
    return {
        "buyer": buyer["id"],
        "seller": seller["id"],
        "status": MatchStatus.INTRO.value,
        "pursued": False,
        **match_details(buyer, seller),
        "created_at": now,
        "updated_at": now,
        "history": [{"status": MatchStatus.INTRO.value, "at": now}],
    }


def _apply_status(match: Dict, new_status: MatchStatus) -> None:
    """Stamp a new status onto the match with history + timestamp."""
    now = _now()
    match["status"] = new_status.value
    match["updated_at"] = now
    match["history"].append({"status": new_status.value, "at": now})


# --------------------------------------------------------------------------- #
# Lifecycle transitions (validate, then apply)
# --------------------------------------------------------------------------- #
def pursue(match: Dict) -> None:
    """intro -> pursued. Sets the permanent ``pursued`` gate."""
    current = MatchStatus(match["status"])
    if current != MatchStatus.INTRO:
        raise TransitionError(
            f"can only pursue a match in 'intro' (currently '{current.value}')"
        )
    match["pursued"] = True
    _apply_status(match, MatchStatus.PURSUED)


def decline(match: Dict) -> None:
    """Any non-terminal stage -> declined (terminal)."""
    current = MatchStatus(match["status"])
    if current in TERMINAL:
        raise TransitionError(
            f"cannot decline a match that is already '{current.value}'"
        )
    _apply_status(match, MatchStatus.DECLINED)


def advance(match: Dict, target: MatchStatus) -> None:
    """Advance a pursued match forward to a later deal stage."""
    current = MatchStatus(match["status"])
    if not match["pursued"]:
        raise TransitionError("match must be pursued before it can advance")
    if current in TERMINAL:
        raise TransitionError(
            f"match is terminal ('{current.value}') and cannot advance"
        )
    target_rank = _RANK.get(target)
    # A valid advance target must be in the pipeline (so not 'declined') and sit
    # past 'pursued' -- you cannot PATCH back to intro/pursued.
    if target_rank is None or target_rank < _MIN_ADVANCE_RANK:
        allowed = ", ".join(s.value for s in PIPELINE[_MIN_ADVANCE_RANK:])
        raise TransitionError(
            f"cannot set status to '{target.value}' via update; allowed: {allowed}"
        )
    if target_rank <= _RANK[current]:
        raise TransitionError(
            f"cannot move backward from '{current.value}' to '{target.value}'"
        )
    _apply_status(match, target)


# --------------------------------------------------------------------------- #
# Matchmaking / reconciliation
# --------------------------------------------------------------------------- #
def _as_pair(entity: Dict, counterparty: Dict) -> Tuple[Dict, Dict]:
    """Order the two entities as ``(buyer, seller)``, whichever is which."""
    return (entity, counterparty) if entity["type"] == "buyer" else (counterparty, entity)


def reconcile_matches(entity: Dict) -> None:
    """Bring a buyer's or seller's ``intro`` matches in line with current state.

    In a single pass this creates matches for newly-compatible active
    counterparties, deletes ``intro`` matches whose pair is no longer compatible
    (an inactive entity is compatible with nobody), and leaves everything else
    untouched -- an existing pair keeps its match, and any match past ``intro``
    represents a real in-flight deal and is never auto-removed.

    It is symmetric across buyers and sellers: it reads ``entity["type"]`` to
    pick the opposite side, and ``match[entity["type"]]`` is always this entity's
    own side of a match.
    """
    other_type = "seller" if entity["type"] == "buyer" else "buyer"
    counterparties = memory.all_sellers() if other_type == "seller" else memory.all_buyers()
    # Desired = every compatible, active counterparty (``is_compatible`` requires
    # both sides active, so an inactive entity desires nobody).
    desired = {
        c["id"]: c for c in counterparties if is_compatible(*_as_pair(entity, c))
    }
    # Reconcile against the matches that already exist for this entity.
    for match in memory.all_matches():
        if match[entity["type"]] != entity["id"]:
            continue
        other_id = match[other_type]
        if match["status"] == MatchStatus.INTRO.value:
            if other_id in desired:
                del desired[other_id]        # already matched -- leave it
            else:
                memory.remove_match(match)   # no longer compatible -- drop it
        else:
            desired.pop(other_id, None)      # progressed deal -- never recreate
    # Whatever is left is a newly-compatible pair with no match yet.
    for counterparty in desired.values():
        memory.add_match(new_match(*_as_pair(entity, counterparty)))
