"""Tests for the hard-coded start-up data in ``app.seed_data``.

The data is frozen literals rather than something computed at boot, which means
nothing stops it drifting out of step with the rules the app enforces. These
tests are what catches that: they assert the seeded store satisfies the same
invariants ``reconcile_matches`` maintains, so an edit to ``seed_data.py`` that
contradicts the matching rules fails here rather than surfacing as matches
silently appearing or vanishing on the first write to a seeded buyer.

The other thing being protected is isolation: loading is bound to the
application lifespan, so a bare ``TestClient(app)`` still starts from an empty
store. Every other test in this suite builds its own fixtures and counts on that.
"""
from collections import Counter

from fastapi.testclient import TestClient

from app import memory, seed
from app.internal.match import MatchStatus, is_compatible
from app.main import app


# --------------------------------------------------------------------------- #
# Isolation
# --------------------------------------------------------------------------- #
def test_bare_testclient_does_not_seed(client):
    """No lifespan, no seed -- what the rest of the suite relies on."""
    assert client.get("/buyers").json() == []
    assert client.get("/sellers").json() == []


def test_lifespan_seeds_the_store():
    """Entering the client as a context manager runs start-up, which seeds."""
    with TestClient(app) as seeded:
        assert len(seeded.get("/buyers").json()) > 0
        assert len(seeded.get("/sellers").json()) > 0


# --------------------------------------------------------------------------- #
# Contents
# --------------------------------------------------------------------------- #
def test_seed_populates_all_three_collections():
    counts = seed.load_seed()
    assert counts["buyers"] > 0
    assert counts["sellers"] > counts["buyers"]
    assert counts["matches"] > 0


def test_every_compatible_active_pair_has_a_match():
    """The invariant reconcile_matches maintains."""
    seed.load_seed()
    pairs = {(m["buyer"], m["seller"]) for m in memory.all_matches()}
    for buyer in memory.all_buyers():
        for seller in memory.all_sellers():
            if is_compatible(buyer, seller):
                assert (buyer["id"], seller["id"]) in pairs


def test_no_intro_match_survives_on_an_incompatible_pair():
    seed.load_seed()
    for match in memory.all_matches():
        if match["status"] == MatchStatus.INTRO.value:
            buyer = memory.get_buyer(match["buyer"])
            seller = memory.get_seller(match["seller"])
            assert is_compatible(buyer, seller)


def test_progressed_matches_carry_the_pursued_flag():
    seed.load_seed()
    for match in memory.all_matches():
        if match["status"] not in (MatchStatus.INTRO.value, MatchStatus.DECLINED.value):
            assert match["pursued"] is True


def test_match_history_is_coherent():
    """Built by real transitions, so history brackets the current status."""
    seed.load_seed()
    for match in memory.all_matches():
        assert match["history"][0]["status"] == MatchStatus.INTRO.value
        assert match["history"][-1]["status"] == match["status"]


def test_seed_spans_the_pipeline():
    """Every stage is populated -- a scenario can query any of them."""
    seed.load_seed()
    seen = Counter(m["status"] for m in memory.all_matches())
    for status in MatchStatus:
        assert seen[status.value] > 0, f"no seeded match at {status.value}"


def test_seed_includes_inactive_listings():
    seed.load_seed()
    statuses = {s["status"] for s in memory.all_sellers()}
    assert "inactive" in statuses


def test_every_buyer_has_matches():
    seed.load_seed()
    per_buyer = Counter(m["buyer"] for m in memory.all_matches())
    for buyer in memory.all_buyers():
        assert per_buyer[buyer["id"]] > 0


def test_reseed_is_idempotent():
    first = seed.reseed()
    second = seed.reseed()
    assert first == second


def test_loading_twice_does_not_accumulate():
    """The literals are copied, not handed out -- so edits cannot leak back."""
    seed.load_seed()
    before = len(memory.all_matches())
    memory.all_matches()[0]["history"].append({"status": "tampered", "at": "now"})
    seed.load_seed()
    assert len(memory.all_matches()) == before
    assert all(e["status"] != "tampered" for e in memory.all_matches()[0]["history"])


def test_ids_are_unique_and_matches_reference_real_parties():
    seed.load_seed()
    buyer_ids = {b["id"] for b in memory.all_buyers()}
    seller_ids = {s["id"] for s in memory.all_sellers()}
    assert len(buyer_ids) == len(memory.all_buyers())
    assert len(seller_ids) == len(memory.all_sellers())
    for match in memory.all_matches():
        assert match["buyer"] in buyer_ids
        assert match["seller"] in seller_ids


def test_counters_sit_past_the_seeded_ids(client):
    """A newly created buyer must not collide with a seeded one."""
    seed.load_seed()
    highest = max(b["id"] for b in memory.all_buyers())
    created = client.post("/buyers", json={
        "name": "Newcomer Capital", "lower_limit": 1, "upper_limit": 2,
        "geographies": ["NY"], "industries": [2755],
    })
    assert created.status_code == 201
    assert created.json()["id"] > highest


# --------------------------------------------------------------------------- #
# Reachable through the API
# --------------------------------------------------------------------------- #
def test_seeded_buyer_exposes_matches_and_recommendations(client):
    seed.load_seed()
    buyer = client.get("/buyers").json()[0]
    assert client.get(f"/buyers/{buyer['id']}/matches").status_code == 200
    assert client.get(f"/buyers/{buyer['id']}/recommendations").status_code == 200


def test_seeded_stats_are_populated(client):
    seed.load_seed()
    stats = client.get("/buyers/stats").json()
    assert stats["count"] > 0
    assert stats["low"] is not None and stats["high"] is not None
