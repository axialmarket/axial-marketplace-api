"""Shared pytest fixtures and payload helpers.

Every test runs against a freshly-reset in-memory store so tests never leak
state into one another.
"""
import pytest
from fastapi.testclient import TestClient

from app import memory
from app.main import app

# Real taxonomy ids (see app/data/industries.csv):
#   263  (root)  -> descendants include 2755, 2756, 6699 ...
#   2755 (mid)   -> parent 263, descendants include 6699
#   6699 (leaf)  -> parent 2755
# So 6699 is a descendant of 2755, but 2755 is NOT a descendant of 6699.
INDUSTRY_PARENT = 2755
INDUSTRY_CHILD = 6699
INDUSTRY_UNRELATED = 2756  # descends from 263 but not from 2755


@pytest.fixture(autouse=True)
def reset_memory():
    memory.reset()
    yield
    memory.reset()


@pytest.fixture
def client():
    return TestClient(app)


def buyer_payload(**overrides):
    payload = {
        "name": "Acme Capital",
        "lower_limit": 100,
        "upper_limit": 1000,
        "geographies": ["NY", "TX"],
        "industries": [INDUSTRY_PARENT],
    }
    payload.update(overrides)
    return payload


def seller_payload(**overrides):
    payload = {
        "name": "Widget Co",
        "selling_price": 500,
        "geography": "NY",
        "industries": [INDUSTRY_CHILD],
    }
    payload.update(overrides)
    return payload


def create_buyer(client, **overrides):
    resp = client.post("/buyers", json=buyer_payload(**overrides))
    assert resp.status_code == 201, resp.text
    return resp.json()


def create_seller(client, **overrides):
    resp = client.post("/sellers", json=seller_payload(**overrides))
    assert resp.status_code == 201, resp.text
    return resp.json()
