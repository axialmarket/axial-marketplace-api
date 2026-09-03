# `industries.csv` — the industry taxonomy

This file holds the **industry taxonomy** the marketplace matches buyers and
sellers against. It represents a *forest* — several independent tree structures
of related "industry" nodes (a broad category at the top, narrowing into
sub-categories toward the leaves).

The industry *names* have been stripped out on purpose; only the numeric ids and
their relationships remain, and the taxonomy has been reduced to the nodes this
challenge actually uses — every id the seed references, plus the ancestors needed
to walk up from it. The `parent_ids` and `children_ids` closures are recomputed
over that surviving set, so they stay internally consistent. It is stored as a flat, pre-computed CSV rather than
a real database or graph structure to **keep it simple for the sake of the
take-home** — a candidate can load and reason about it with nothing more than
the standard library.

## Format

Pipe-delimited (`|`), one node per row, no header:

```
node_id | parent_id | ancestor_ids | descendant_ids
```

| Column | Meaning |
|---|---|
| `node_id` | Unique id for this node. |
| `parent_id` | The immediate parent's id. **Empty** when the node is the top (root) of its tree. |
| `ancestor_ids` | Comma-separated closure of every ancestor up to the root, **including the node itself**. |
| `descendant_ids` | Comma-separated closure of every descendant down to the leaves, **including the node itself**. |

Both closures include the node itself, which makes membership tests trivial:

* *Is X a descendant of (or equal to) Y?* → `X in Y.descendant_ids`
* *Is X an ancestor of (or equal to) Y?* → `X in Y.ancestor_ids`

## Example

```
2755|263|263,2755|2755,6699,6700,15463,15464,15465,15466,15467,15468,15469,15470
```

* Node `2755`'s parent is `263`.
* Its ancestors are `{263, 2755}` — so `263` sits directly above it, at the root.
* Its descendants are `{2755, 6699, 6700, 15463…15470}` — so `6699` is one of its
  sub-categories.

A row whose `parent_id` is empty (e.g. `263`) is a root node.

## How it's used

The taxonomy is loaded once at startup by
[`app/internal/industries.py`](../internal/industries.py) into an in-memory
index of `IndustryNode` objects. Buyer/seller **industry matching** relies on
the descendant relationship: a seller matches a buyer when one of the seller's
industries equals, or is a descendant of, one of the buyer's industries.
