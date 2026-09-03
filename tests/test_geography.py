"""Tests for the US geography reference.

Nothing in the strict matching rules consults this -- a geography there is an
opaque string, and two geographies either are or are not equal. It is reference
data for matching schemes that need to reason about *nearness*: which states
adjoin which, and which region a state sits in.

Because nothing in the app exercises it yet, these tests are the only thing
standing between a bad regeneration and silently wrong widening later. They
assert the shape of the data, not a handful of spot values.
"""
from app.internal.geography import (
    REGION_STATES,
    STATE_BORDERS,
    STATE_NAMES,
    STATE_REGION,
    all_states,
    load_geographies,
    neighbours,
    regions_of,
)


# --------------------------------------------------------------------------- #
# Shape of the data
# --------------------------------------------------------------------------- #
def test_the_reference_loads():
    assert len(all_states()) == 51           # 50 states plus DC
    assert STATE_NAMES["NY"] == "New York"
    assert STATE_REGION["NY"] == "Middle Atlantic"


def test_every_state_has_a_region():
    for code in all_states():
        assert code in STATE_REGION, f"{code} has no region"


def test_every_state_has_at_least_one_neighbour():
    """Alaska and Hawaii included -- they are given a nearest mainland state."""
    for code in all_states():
        assert STATE_BORDERS[code], f"{code} has no neighbours"


def test_regions_partition_the_states():
    covered = set().union(*REGION_STATES.values())
    assert covered == all_states()
    # No state in two regions.
    assert sum(len(states) for states in REGION_STATES.values()) == len(all_states())


def test_adjacency_is_symmetric():
    """If A borders B then B borders A. Asymmetry means the data is wrong.

    This is what caught Indiana being listed against Missouri and Wisconsin --
    which it does not touch -- while missing Michigan and Ohio, which both listed
    Indiana themselves.
    """
    asymmetric = [
        (code, other)
        for code, others in STATE_BORDERS.items()
        for other in others
        if code not in STATE_BORDERS.get(other, ())
    ]
    assert not asymmetric, f"asymmetric border pairs: {asymmetric}"


def test_no_state_borders_itself():
    assert not [code for code, others in STATE_BORDERS.items() if code in others]


def test_every_neighbour_is_a_known_state():
    known = all_states()
    for code, others in STATE_BORDERS.items():
        unknown = set(others) - known
        assert not unknown, f"{code} borders unknown states: {unknown}"


def test_indiana_borders_are_correct():
    """A regression guard on the one row the upstream table had wrong."""
    assert set(STATE_BORDERS["IN"]) == {"IL", "KY", "MI", "OH"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def test_neighbours_includes_the_states_asked_for():
    result = neighbours(["NY"])
    assert "NY" in result
    assert result == {"NY", *STATE_BORDERS["NY"]}


def test_neighbours_of_several_states_is_the_union():
    assert neighbours(["NY", "CA"]) == neighbours(["NY"]) | neighbours(["CA"])


def test_regions_of_returns_every_state_in_the_region():
    result = regions_of(["NY"])
    assert result == set(REGION_STATES["Middle Atlantic"])
    assert "NY" in result


def test_unknown_codes_are_carried_through_not_dropped():
    """A caller that invented a geography should see it fail to match later.

    Dropping it would be worse than useless: the widened set would silently
    become *narrower* than what was asked for.
    """
    assert "ZZ" in neighbours(["ZZ"])
    assert "ZZ" in regions_of(["ZZ"])
    assert regions_of(["ZZ", "NY"]) == {"ZZ"} | set(REGION_STATES["Middle Atlantic"])


def test_reloading_is_idempotent():
    before = (dict(STATE_NAMES), dict(STATE_BORDERS), dict(STATE_REGION))
    load_geographies()
    assert (STATE_NAMES, STATE_BORDERS, STATE_REGION) == before
