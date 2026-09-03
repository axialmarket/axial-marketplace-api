"""US geography reference: which states border which, and which region each is in.

Loaded once at import time from ``app/data/geographies.csv``, one state per row,
pipe-delimited::

    code | name | region | comma-separated bordering codes

The strict matching rules in :mod:`app.internal.match` never need any of this --
a geography there is an opaque string, and two geographies either are or are not
equal. It exists for the DYML scheme (:mod:`app.internal.dyml`), which widens a
buyer's stated geographies outward in steps: bordering states, then the region
those states sit in, then the whole country. That walk needs a hierarchy.

Codes are the same two-letter strings buyers and sellers use, so nothing needs
translating at the boundary.
"""
import csv
from pathlib import Path
from typing import Dict, FrozenSet, List, Set, Tuple

_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "geographies.csv"

#: ``{code: full name}``
STATE_NAMES: Dict[str, str] = {}

#: ``{code: region name}``
STATE_REGION: Dict[str, str] = {}

#: ``{region name: frozenset of state codes}``
REGION_STATES: Dict[str, FrozenSet[str]] = {}

#: ``{code: tuple of bordering state codes}``. Every state has at least one entry
#: -- Alaska and Hawaii are given their nearest mainland neighbour rather than
#: left isolated, which is what the reference data does.
STATE_BORDERS: Dict[str, Tuple[str, ...]] = {}


def load_geographies(csv_path: Path = _CSV_PATH) -> None:
    """Populate the module-level indexes from the CSV."""
    STATE_NAMES.clear()
    STATE_REGION.clear()
    REGION_STATES.clear()
    STATE_BORDERS.clear()

    regions: Dict[str, Set[str]] = {}
    with open(csv_path, newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter="|"):
            if not row or row[0].lstrip().startswith("#"):
                continue
            code, name, region, borders = (row + ["", "", ""])[:4]
            code = code.strip()
            STATE_NAMES[code] = name.strip()
            if region.strip():
                STATE_REGION[code] = region.strip()
                regions.setdefault(region.strip(), set()).add(code)
            STATE_BORDERS[code] = tuple(
                sorted(c.strip() for c in borders.split(",") if c.strip())
            )
    REGION_STATES.update({name: frozenset(codes) for name, codes in regions.items()})


def all_states() -> FrozenSet[str]:
    """Every state code the reference knows about."""
    return frozenset(STATE_NAMES)


def neighbours(codes: List[str]) -> Set[str]:
    """``codes`` plus every state bordering one of them."""
    out = set(codes)
    for code in codes:
        out.update(STATE_BORDERS.get(code, ()))
    return out


def regions_of(codes: List[str]) -> Set[str]:
    """Every state sharing a region with one of ``codes``.

    Unknown codes are carried through untouched rather than dropped: a caller
    that invented a geography should see it fail to match, not see it silently
    disappear and widen to something else.
    """
    out: Set[str] = set()
    for code in codes:
        region = STATE_REGION.get(code)
        if region is None:
            out.add(code)
        else:
            out.update(REGION_STATES[region])
    return out


# Load eagerly so importers can rely on the indexes being populated.
load_geographies()
