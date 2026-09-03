"""Matchmaking + match lifecycle tests.

Matches are a sub-resource of buyers and sellers -- there is no top-level
``/matches``. Most tests drive them through the buyer path; a couple use the
seller path to exercise the shared ``match_actions`` code from both sides.
"""
from tests.conftest import (
    INDUSTRY_PARENT,
    INDUSTRY_UNRELATED,
    create_buyer,
    create_seller,
)


def _buyer_matches(client, buyer_id, **params):
    return client.get(f"/buyers/{buyer_id}/matches", params=params).json()


def _make_match(client):
    """Create a compatible buyer/seller and return (buyer, seller, match)."""
    buyer = create_buyer(client)
    seller = create_seller(client)
    match = _buyer_matches(client, buyer["id"])[0]
    return buyer, seller, match


# --------------------------------------------------------------------------- #
# Match generation
# --------------------------------------------------------------------------- #
def test_match_generated_for_compatible_pair(client):
    buyer = create_buyer(client)
    create_seller(client)
    matches = _buyer_matches(client, buyer["id"])
    assert len(matches) == 1
    assert matches[0]["status"] == "intro"
    assert matches[0]["pursued"] is False
    assert matches[0]["buyer"] == buyer["id"]


def test_match_details_snapshot(client):
    buyer = create_buyer(client)
    create_seller(client)
    match = _buyer_matches(client, buyer["id"])[0]
    assert match["matched_geographies"] == ["NY"]
    assert match["matched_industries"] == [6699]
    assert match["score"] > 0


def test_no_match_on_geography_mismatch(client):
    buyer = create_buyer(client, geographies=["TX"])
    create_seller(client, geography="NY")
    assert _buyer_matches(client, buyer["id"]) == []


def test_no_match_on_price_out_of_band(client):
    buyer = create_buyer(client, lower_limit=100, upper_limit=400)
    create_seller(client, selling_price=500)
    assert _buyer_matches(client, buyer["id"]) == []


def test_no_match_on_industry_direction(client):
    # Buyer's industry is the *child*; seller's is the *parent* -> not a descendant.
    buyer = create_buyer(client, industries=[6699])
    create_seller(client, industries=[INDUSTRY_PARENT])
    assert _buyer_matches(client, buyer["id"]) == []


def test_no_match_on_unrelated_industry(client):
    buyer = create_buyer(client, industries=[INDUSTRY_PARENT])
    create_seller(client, industries=[INDUSTRY_UNRELATED])
    assert _buyer_matches(client, buyer["id"]) == []


def test_matchmaking_is_deduplicated(client):
    buyer = create_buyer(client)
    create_seller(client)
    # Updating the buyer re-runs matchmaking but must not create a second match.
    client.put(f"/buyers/{buyer['id']}", json={"upper_limit": 2000})
    assert len(_buyer_matches(client, buyer["id"])) == 1


def test_edit_breaking_compatibility_deletes_intro_match(client):
    # A buyer edit that makes the pair incompatible drops the stale intro match.
    buyer, _, _ = _make_match(client)
    assert len(_buyer_matches(client, buyer["id"])) == 1
    client.put(f"/buyers/{buyer['id']}", json={"geographies": ["CA"]})
    assert _buyer_matches(client, buyer["id"]) == []


def test_edit_breaking_compatibility_preserves_progressed_match(client):
    buyer, _, match = _make_match(client)
    client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/pursue")
    client.put(f"/buyers/{buyer['id']}", json={"geographies": ["CA"]})
    remaining = _buyer_matches(client, buyer["id"])
    assert len(remaining) == 1
    assert remaining[0]["status"] == "pursued"


def test_match_listed_under_buyer_and_seller(client):
    buyer = create_buyer(client)
    seller = create_seller(client)
    assert len(client.get(f"/buyers/{buyer['id']}/matches").json()) == 1
    assert len(client.get(f"/sellers/{seller['id']}/matches").json()) == 1


# --------------------------------------------------------------------------- #
# Ownership: a match is only reachable through its own buyer/seller
# --------------------------------------------------------------------------- #
def test_match_get_under_owning_buyer(client):
    buyer, _, match = _make_match(client)
    resp = client.get(f"/buyers/{buyer['id']}/matches/{match['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == match["id"]


def test_match_not_reachable_under_other_buyer(client):
    _, _, match = _make_match(client)
    other = create_buyer(client, name="Other")
    assert client.get(f"/buyers/{other['id']}/matches/{match['id']}").status_code == 404
    assert (
        client.post(f"/buyers/{other['id']}/matches/{match['id']}/pursue").status_code
        == 404
    )


# --------------------------------------------------------------------------- #
# Lifecycle: pursue / decline
# --------------------------------------------------------------------------- #
def test_pursue_moves_intro_to_pursued(client):
    buyer, _, match = _make_match(client)
    resp = client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/pursue")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pursued"
    assert resp.json()["pursued"] is True


def test_pursue_via_seller_path(client):
    _, seller, match = _make_match(client)
    resp = client.post(f"/sellers/{seller['id']}/matches/{match['id']}/pursue")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pursued"


def test_pursue_twice_conflicts(client):
    buyer, _, match = _make_match(client)
    client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/pursue")
    resp = client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/pursue")
    assert resp.status_code == 409


def test_decline_from_intro(client):
    buyer, _, match = _make_match(client)
    resp = client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/decline")
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"


def test_decline_after_pursue(client):
    buyer, _, match = _make_match(client)
    client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/pursue")
    resp = client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/decline")
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"


def test_decline_terminal_conflicts(client):
    buyer, _, match = _make_match(client)
    client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/decline")
    resp = client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/decline")
    assert resp.status_code == 409


def test_pursue_missing_match_404(client):
    buyer = create_buyer(client)
    assert client.post(f"/buyers/{buyer['id']}/matches/999/pursue").status_code == 404


# --------------------------------------------------------------------------- #
# Lifecycle: advance (PATCH)
# --------------------------------------------------------------------------- #
def _patch(client, buyer_id, match_id, status):
    return client.patch(f"/buyers/{buyer_id}/matches/{match_id}", json={"status": status})


def test_advance_requires_pursued(client):
    buyer, _, match = _make_match(client)
    assert _patch(client, buyer["id"], match["id"], "nda_signed").status_code == 409


def test_advance_forward(client):
    buyer, _, match = _make_match(client)
    client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/pursue")
    resp = _patch(client, buyer["id"], match["id"], "nda_signed")
    assert resp.status_code == 200
    assert resp.json()["status"] == "nda_signed"


def test_advance_allows_forward_skip(client):
    buyer, _, match = _make_match(client)
    client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/pursue")
    resp = _patch(client, buyer["id"], match["id"], "loi_issued")
    assert resp.status_code == 200
    assert resp.json()["status"] == "loi_issued"


def test_advance_backward_conflicts(client):
    buyer, _, match = _make_match(client)
    client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/pursue")
    _patch(client, buyer["id"], match["id"], "loi_issued")
    assert _patch(client, buyer["id"], match["id"], "nda_signed").status_code == 409


def test_advance_to_non_advanceable_state_conflicts(client):
    buyer, _, match = _make_match(client)
    client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/pursue")
    # 'pursued' is not a PATCH-able target.
    assert _patch(client, buyer["id"], match["id"], "pursued").status_code == 409


def test_advance_to_closed_then_locked(client):
    buyer, _, match = _make_match(client)
    client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/pursue")
    _patch(client, buyer["id"], match["id"], "closed")
    assert _patch(client, buyer["id"], match["id"], "loi_issued").status_code == 409
    assert (
        client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/decline").status_code
        == 409
    )


# --------------------------------------------------------------------------- #
# Active/inactive reconciliation
# --------------------------------------------------------------------------- #
def test_inactive_buyer_deletes_intro_match(client):
    buyer, _, _ = _make_match(client)
    assert len(_buyer_matches(client, buyer["id"])) == 1
    client.put(f"/buyers/{buyer['id']}", json={"status": "inactive"})
    assert _buyer_matches(client, buyer["id"]) == []


def test_inactive_buyer_preserves_progressed_match(client):
    buyer, _, match = _make_match(client)
    client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/pursue")
    client.put(f"/buyers/{buyer['id']}", json={"status": "inactive"})
    remaining = _buyer_matches(client, buyer["id"])
    assert len(remaining) == 1
    assert remaining[0]["status"] == "pursued"


def test_reactivating_buyer_recreates_intro_match(client):
    buyer, _, _ = _make_match(client)
    client.put(f"/buyers/{buyer['id']}", json={"status": "inactive"})
    assert _buyer_matches(client, buyer["id"]) == []
    client.put(f"/buyers/{buyer['id']}", json={"status": "active"})
    recreated = _buyer_matches(client, buyer["id"])
    assert len(recreated) == 1
    assert recreated[0]["status"] == "intro"


def test_inactive_seller_not_matched_on_create(client):
    seller = create_seller(client)
    client.put(f"/sellers/{seller['id']}", json={"status": "inactive"})
    buyer = create_buyer(client)  # matchmaking runs, but seller is inactive
    assert _buyer_matches(client, buyer["id"]) == []


def test_delete_buyer_cascades_to_matches(client):
    buyer, seller, match = _make_match(client)
    client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/pursue")  # progressed too
    client.delete(f"/buyers/{buyer['id']}")
    # Buyer is gone; check via the still-present seller that the match went too.
    assert client.get(f"/sellers/{seller['id']}/matches").json() == []


def test_filter_matches_by_status(client):
    buyer, _, match = _make_match(client)
    client.post(f"/buyers/{buyer['id']}/matches/{match['id']}/pursue")
    assert len(_buyer_matches(client, buyer["id"], status="pursued")) == 1
    assert _buyer_matches(client, buyer["id"], status="intro") == []
