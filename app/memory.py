"""The global in-memory data store.

There is **no persistence**. This is a take-home assessment, so the store lives
entirely in process memory: it starts empty when the server boots, fills up as
API calls create buyers, sellers and matches, and is discarded when the server
shuts down.

Every stored object is a dict tagged with a ``type`` (``"buyer"``, ``"seller"``
or ``"match"``) and an integer ``id``, both stamped on by the ``add_*``
functions below. That ``type`` tag is what lets the matchmaking code treat
buyers and sellers with one symmetric code path instead of branching on a
``kind`` argument.

Everything else in the app -- routers and utility functions -- goes through the
small function API below rather than touching the raw ``MEMORY`` dict, so the
storage shape and its id generation live in exactly one place.

Internal layout (private; use the functions instead)::

    MEMORY = {
        "buyers":   {buyer_id:  buyer_dict},
        "sellers":  {seller_id: seller_dict},
        "matches":  {match_id:  match_dict},
        "counters": {"buyer": int, "seller": int, "match": int},
    }
"""
from typing import Dict, List, Optional


def _empty_store() -> Dict:
    return {
        "buyers": {},
        "sellers": {},
        "matches": {},
        "counters": {"buyer": 0, "seller": 0, "match": 0},
    }


MEMORY: Dict = _empty_store()


# --------------------------------------------------------------------------- #
# Store lifecycle / ids (internal helpers)
# --------------------------------------------------------------------------- #
def reset() -> None:
    """Wipe the store back to empty. Used by the test-suite between tests."""
    MEMORY.clear()
    MEMORY.update(_empty_store())


def _next_id(kind: str) -> int:
    """Return the next monotonic integer id for ``kind`` (buyer/seller/match)."""
    MEMORY["counters"][kind] += 1
    return MEMORY["counters"][kind]


def load(buyers: List[Dict], sellers: List[Dict], matches: List[Dict]) -> None:
    """Replace the store with pre-built objects, keeping the ids they carry.

    This is how ``app.seed`` installs the hard-coded starting data. Unlike the
    ``add_*`` functions it does not stamp ids -- the objects already have them,
    and the matches reference buyers and sellers by those ids, so reassigning
    would break the links. The counters are then set past the highest id in each
    collection so anything created afterwards does not collide.
    """
    reset()
    MEMORY["buyers"] = {b["id"]: b for b in buyers}
    MEMORY["sellers"] = {s["id"]: s for s in sellers}
    MEMORY["matches"] = {m["id"]: m for m in matches}
    MEMORY["counters"] = {
        "buyer": max((b["id"] for b in buyers), default=0),
        "seller": max((s["id"] for s in sellers), default=0),
        "match": max((m["id"] for m in matches), default=0),
    }


# --------------------------------------------------------------------------- #
# Buyers
# --------------------------------------------------------------------------- #
def add_buyer(buyer: Dict) -> Dict:
    """Stamp ``type``/``id`` on the buyer, store it, and return it."""
    buyer["type"] = "buyer"
    buyer["id"] = _next_id("buyer")
    MEMORY["buyers"][buyer["id"]] = buyer
    return buyer


def get_buyer(buyer_id: int) -> Optional[Dict]:
    return MEMORY["buyers"].get(buyer_id)


def all_buyers() -> List[Dict]:
    return list(MEMORY["buyers"].values())


def remove_buyer(buyer: Dict) -> None:
    MEMORY["buyers"].pop(buyer["id"], None)


# --------------------------------------------------------------------------- #
# Sellers
# --------------------------------------------------------------------------- #
def add_seller(seller: Dict) -> Dict:
    """Stamp ``type``/``id`` on the seller, store it, and return it."""
    seller["type"] = "seller"
    seller["id"] = _next_id("seller")
    MEMORY["sellers"][seller["id"]] = seller
    return seller


def get_seller(seller_id: int) -> Optional[Dict]:
    return MEMORY["sellers"].get(seller_id)


def all_sellers() -> List[Dict]:
    return list(MEMORY["sellers"].values())


def remove_seller(seller: Dict) -> None:
    MEMORY["sellers"].pop(seller["id"], None)


# --------------------------------------------------------------------------- #
# Matches
# --------------------------------------------------------------------------- #
def add_match(match: Dict) -> Dict:
    """Stamp ``type``/``id`` on the match, store it, and return it."""
    match["type"] = "match"
    match["id"] = _next_id("match")
    MEMORY["matches"][match["id"]] = match
    return match


def get_match(match_id: int) -> Optional[Dict]:
    return MEMORY["matches"].get(match_id)


def all_matches() -> List[Dict]:
    return list(MEMORY["matches"].values())


def remove_match(match: Dict) -> None:
    MEMORY["matches"].pop(match["id"], None)
