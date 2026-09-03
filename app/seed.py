"""Install the hard-coded starting data into the in-memory store.

The data itself lives in :mod:`app.seed_data` as plain literals. Nothing is
computed here -- no matchmaking, no file parsing, no clock. The literals are
copied in as they are, so the store the server boots with is identical every
time and is exactly what is written in that file.

Those literals were *produced* by running the app's own rules (see
``interview-db/freeze_seed.py``), so the starting store already satisfies the
invariants ``reconcile_matches`` enforces. Edit ``seed_data.py`` to change the
starting world for a scenario.
"""
from copy import deepcopy
from typing import Dict

from app import memory
from app.seed_data import BUYERS, MATCHES, SELLERS


def load_seed() -> Dict[str, int]:
    """Replace the store with the seed data. Returns a count of what was loaded.

    Deep-copied on the way in: the store is mutated in place by the API (a PUT
    edits the buyer dict, a lifecycle transition appends to a match's history),
    and without a copy those edits would accumulate in the module-level literals
    and leak into the next load.
    """
    memory.load(deepcopy(BUYERS), deepcopy(SELLERS), deepcopy(MATCHES))
    return {
        "buyers": len(BUYERS),
        "sellers": len(SELLERS),
        "matches": len(MATCHES),
        "progressed": sum(1 for m in MATCHES if m["status"] != "intro"),
    }


#: ``load_seed`` already clears the store, so this is just a readable alias for
#: "put everything back the way it started".
reseed = load_seed


def summary(counts: Dict[str, int]) -> str:
    """One-line description of a :func:`load_seed` result, for start-up logging."""
    return (f"seeded {counts['buyers']} buyers, {counts['sellers']} sellers, "
            f"{counts['matches']} matches ({counts['progressed']} past intro)")
