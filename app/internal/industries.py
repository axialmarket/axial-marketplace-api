"""Industry taxonomy tree.

The taxonomy is a forest (several independent trees) loaded once at import time
from ``app/data/industries.csv``. Each row is pipe-delimited::

    node_id | parent_id | parent_ids | children_ids

* ``parent_ids``   is the full ancestor chain *including self* (root-ward).
* ``children_ids`` is the full descendant set *including self* (leaf-ward).

Because those closures are precomputed, "is X a descendant of Y?" is a single
set membership test: ``X in node(Y).children_ids``.
"""
import csv
from pathlib import Path
from typing import Dict, Optional, Set

_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "industries.csv"


class IndustryNode:
    """A single node in the industry taxonomy."""

    __slots__ = ("node_id", "parent_id", "parent_ids", "children_ids")

    def __init__(
        self,
        node_id: int,
        parent_id: Optional[int],
        parent_ids: Set[int],
        children_ids: Set[int],
    ) -> None:
        # Unique id for this node.
        self.node_id = node_id
        # Immediate parent, or None if this node is the top of its tree.
        self.parent_id = parent_id
        # Every ancestor up to the root, including self.
        self.parent_ids = parent_ids
        # Every descendant down to the leaves, including self.
        self.children_ids = children_ids

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"IndustryNode(id={self.node_id}, parent={self.parent_id}, "
            f"ancestors={len(self.parent_ids)}, descendants={len(self.children_ids)})"
        )


# { node_id: IndustryNode }
INDUSTRY_INDEX: Dict[int, IndustryNode] = {}


def _parse_int_set(field: str) -> Set[int]:
    """Convert an ``'int,int,int'`` field into a set of ints."""
    return {int(x.strip()) for x in field.split(",") if x.strip()}


def load_industries(csv_path: Path = _CSV_PATH) -> Dict[int, IndustryNode]:
    """Populate and return ``INDUSTRY_INDEX`` from the CSV file."""
    INDUSTRY_INDEX.clear()
    with open(csv_path, newline="") as csvfile:
        for row in csv.reader(csvfile, delimiter="|"):
            node_id = int(row[0])
            INDUSTRY_INDEX[node_id] = IndustryNode(
                node_id=node_id,
                parent_id=int(row[1]) if row[1] else None,
                parent_ids=_parse_int_set(row[2]),
                children_ids=_parse_int_set(row[3]),
            )
    return INDUSTRY_INDEX


def get_industry_node(node_id: int) -> Optional[IndustryNode]:
    """Look up an industry node by id, or ``None`` if it does not exist."""
    return INDUSTRY_INDEX.get(node_id)


def is_descendant(candidate_id: int, ancestor_id: int) -> bool:
    """True if ``candidate_id`` equals or is a descendant of ``ancestor_id``."""
    ancestor = INDUSTRY_INDEX.get(ancestor_id)
    if ancestor is None:
        return False
    return candidate_id in ancestor.children_ids


# Load eagerly so importers can rely on the index being populated.
load_industries()
