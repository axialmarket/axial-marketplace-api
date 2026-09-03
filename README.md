# Axial Marketplace API — Interview Challenge

A small [FastAPI](https://fastapi.tiangolo.com/) service that models a
buyer/seller marketplace on top of an industry taxonomy. Buyers and sellers are
matched into **Match** objects, each of which follows a deal-pipeline lifecycle.

This repo is structured as a
[bigger application](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
(a `main.py` plus a `routers/` package) and stores all state in a single
in-memory dictionary — there is no database. That store is **pre-populated with
hard-coded data**, so the API comes up with a marketplace already in motion
rather than empty.

## Running it

Needs **Python 3.9 or newer** (tested on 3.9 through 3.13) and
[uv](https://docs.astral.sh/uv/), on macOS or Linux.

<details>
<summary>Installing uv</summary>

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # the official installer
brew install uv                                   # or, with Homebrew
pip install uv                                    # or, into a Python you already have
```

uv can supply the interpreter too, which is the easiest fix if your system Python
is older than 3.9:

```bash
uv python install 3.13
uv venv --python 3.13 .venv
```
</details>

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/docs for interactive API docs. The server starts
with 12 buyers, 102 sellers and 92 matches already loaded — see
[Seed data](#seed-data).

Nothing here depends on uv — the standard library works just as well, it is only
slower:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Running the tests

```bash
python -m pytest
```

`pytest.ini` puts the repo root on the path, so this works from here with no
`PYTHONPATH` set.

## Layout

```
app/
  main.py            # FastAPI app, wires the routers together, seeds on start-up
  memory.py          # the global in-memory store + the function API for it
                     #   (add/get/all/remove for buyers, sellers, matches)
  seed.py            # copies seed_data into the store at start-up
  seed_data.py       # the starting buyers, sellers and matches, as literals
  schemas.py         # shared schemas (EntityStatus, Stats, Recommendation) + match models
  dependencies.py    # shared lookups that 404 on missing entities
  data/
    industries.csv   # the industry taxonomy (pipe-delimited forest)
    geographies.csv  # US states: name, region, bordering states
  internal/
    industries.py    # taxonomy loader + IndustryNode + ancestor/descendant checks
    geography.py     # US states: borders and regions (reference data, see below)
    buyer.py         # a buyer: schema, new_buyer, stats + recommendations
    seller.py        # a seller: schema, new_seller, stats + recommendations
    match.py         # a match: compatibility + scoring, structure, lifecycle,
                     #   and reconcile_matches (matchmaking)
  routers/
    buyers.py        # buyer CRUD, stats, recommendations, + matches sub-resource
    sellers.py       # seller CRUD, stats, recommendations, + matches sub-resource
tests/               # full pytest suite (TestClient based)
```

## Seed data

The store starts populated, so every scenario opens against a working
marketplace: **12 buyers, 102 sellers and 92 matches**, spread across all seven
pipeline stages and including inactive listings. Every buyer holds between 5 and
10 matches.

The data is hard-coded in [`app/seed_data.py`](app/seed_data.py) as plain Python
literals — `BUYERS`, `SELLERS`, `MATCHES`. Nothing is computed at boot:
`app.seed` deep-copies those literals into `app.memory` and that is the whole of
it. No matchmaking runs, no files are parsed, no clock is read, so the store the
server comes up with is byte-identical every time and is exactly what is written
in that file.

The names are invented. Price bands, US states, industry ids and the spread of
deal outcomes are drawn from real marketplace activity.

### Editing it

`seed_data.py` is where you change the starting world for a scenario. It is
generated (see the header in the file), but hand-editing is fine — with one
caveat worth understanding.

The literals are *not* checked when they load. They were produced by running the
app's own rules, so they start out consistent, but nothing stops an edit from
contradicting those rules, and the app will then quietly correct you: the first
`POST`/`PUT` touching a seeded buyer or seller runs `reconcile_matches`, which
creates matches for compatible pairs that lack one and deletes `intro` matches
whose pair is no longer compatible. An inconsistent seed therefore does not fail
loudly — it drifts on first write.

Two invariants keep you out of that:

* every compatible pair of **active** buyer and seller needs a match, and no
  `intro` match may exist for a pair that is not compatible;
* a match past `intro` must carry `pursued: true`, and its `history` must start
  at `intro` and end at its current `status`.

[`tests/test_seed.py`](tests/test_seed.py) asserts both, so run the suite after
editing and an inconsistent seed fails there instead of surprising you later.

### Loading it yourself

Loading is bound to the application lifespan, so it runs for a real server but
**not** for a bare `TestClient(app)` — the test suite builds its own fixtures and
starts from empty. Use `with TestClient(app)` for a seeded app, or call it
directly:

```python
from app import seed

seed.load_seed()   # replace the store with the seed data
seed.reseed()      # the same thing, named for when you want a clean slate
```

## Domain model

### Buyers & sellers

* Both are created via `POST` and returned with a generated integer **`id`**;
  everything references them by id.
* Both carry a `status` of `active` or `inactive` (default `active`). The update
  endpoint can flip it.
* A **buyer** has a price band (`lower_limit`/`upper_limit`), a list of
  `geographies`, and a list of `industries`.
* A **seller** has a single `selling_price`, a single `geography`, and a list of
  `industries`.

### Geography reference

A geography is an opaque string as far as the matching rules are concerned: two
geographies either are or are not equal, and `"NY"` is no closer to `"NJ"` than
to `"HI"`.

[`app/internal/geography.py`](app/internal/geography.py) adds the structure that
comparison throws away — for each of the 51 states (50 plus DC), which states
adjoin it and which of the nine regions it belongs to:

```python
from app.internal.geography import neighbours, regions_of, STATE_REGION

STATE_REGION["NY"]        # 'Middle Atlantic'
neighbours(["NY"])        # {'NY', 'CT', 'MA', 'NJ', 'PA', 'VT'}
regions_of(["NY"])        # every state in the Middle Atlantic
```

**Nothing in the rules below uses it.** It is here for matching schemes that need
to reason about nearness rather than equality, and it is loaded eagerly at import
so it is simply available.

Unknown codes are carried through both helpers rather than dropped — a caller who
invents a geography should see it fail to match, not watch a widened set quietly
become narrower than what was asked for.

### Compatibility

A buyer and seller are compatible (the original take-home rules — the relation
is symmetric) when **all** hold:

* **geography** — the seller's geography is one of the buyer's geographies;
* **price band** — `lower_limit <= selling_price <= upper_limit`;
* **industry** — some seller industry equals, or is a *descendant* of, some
  buyer industry in the taxonomy.

Industry direction matters: a buyer in a broad category matches a seller in a
narrower sub-category, but not vice-versa.

### Matches & matchmaking

Every stored object carries a `type` (`buyer`/`seller`/`match`) and an `id`. A
**Match** records its two parties as `match.buyer` and `match.seller` (their
ids) and snapshots its `score` and the matched geographies/industries at
creation time, so its lifecycle is independent of later edits to either party.

Creating or updating a buyer/seller **reconciles** that entity's matches in a
single pass (`reconcile_matches`):

* **create** a fresh `intro` match for every compatible, active counterparty
  that has no match yet;
* **delete** `intro` matches whose pair is no longer compatible — because the
  entity went inactive, or an edit moved it out of the price band / geography /
  industry overlap. There is no stored "inactive" match;
* **leave** everything else untouched — a pair that already has a match keeps
  it, and any match past `intro` represents a real in-flight deal and is never
  auto-removed.

Because each object knows its own `type`, this one code path serves buyers and
sellers with no per-side branching. A hard `DELETE` is separate: it removes the
entity and *every* match referencing it, progressed ones included.

### Match lifecycle

```
intro ─pursue→ pursued ─┬─ nda_signed ─ cim_exchanged ─ loi_issued ─ closed
                        │        (advance via PATCH; forward-only)
  └──────────── decline (from any live stage) ─────────────→ declined
```

Matches are a **sub-resource** of buyers and sellers — there is no top-level
`/matches`. Every action is reachable through either party the match belongs to
(`{parent}` = `/buyers/{buyer_id}` or `/sellers/{seller_id}`):

* `POST {parent}/matches/{id}/pursue` — `intro → pursued`; sets the permanent `pursued` flag.
* `POST {parent}/matches/{id}/decline` — any live stage → `declined` (terminal).
* `PATCH {parent}/matches/{id}` — advances a **pursued** match forward to a later
  deal stage. Forward skips are allowed; backward moves and non-pipeline targets
  are rejected. A match that has never been pursued cannot be advanced.

Requesting a match through a buyer/seller it does not belong to returns
`404`. `closed` and `declined` are terminal. Invalid transitions return
`409 Conflict`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/buyers` | Create a buyer (runs matchmaking) |
| `GET` | `/buyers` | List buyers (filter: `status`, `geography`, `industry`; paginate) |
| `GET` | `/buyers/stats` | Low/high price limits across buyers |
| `GET` | `/buyers/{id}` | Fetch a buyer |
| `PUT` | `/buyers/{id}` | Partial update (runs matchmaking / cleanup) |
| `DELETE` | `/buyers/{id}` | Hard-delete a buyer + its matches |
| `GET` | `/buyers/{id}/recommendations` | Live-ranked compatible sellers |
| `GET` | `/buyers/{id}/matches` | Buyer's matches (filter: `status`) |
| `GET` | `/buyers/{id}/matches/{mid}` | Fetch one of the buyer's matches |
| `POST` | `/buyers/{id}/matches/{mid}/pursue` | Pursue the match |
| `POST` | `/buyers/{id}/matches/{mid}/decline` | Decline the match |
| `PATCH` | `/buyers/{id}/matches/{mid}` | Advance the pursued match |
| `POST` | `/sellers` | Create a seller (runs matchmaking) |
| `GET` | `/sellers` | List sellers (filter + paginate) |
| `GET` | `/sellers/stats` | Low/high asking price across sellers |
| `GET` | `/sellers/{id}` | Fetch a seller |
| `PUT` | `/sellers/{id}` | Partial update (runs matchmaking / cleanup) |
| `DELETE` | `/sellers/{id}` | Hard-delete a seller + its matches |
| `GET` | `/sellers/{id}/recommendations` | Live-ranked compatible buyers |
| `GET` | `/sellers/{id}/matches` | Seller's matches (filter: `status`) |
| `GET` | `/sellers/{id}/matches/{mid}` | Fetch one of the seller's matches |
| `POST` | `/sellers/{id}/matches/{mid}/pursue` | Pursue the match |
| `POST` | `/sellers/{id}/matches/{mid}/decline` | Decline the match |
| `PATCH` | `/sellers/{id}/matches/{mid}` | Advance the pursued match |
