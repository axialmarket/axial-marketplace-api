from tests.conftest import create_seller, seller_payload


def test_create_seller_returns_object_with_id(client):
    body = create_seller(client)
    assert body["id"] == 1
    assert body["status"] == "active"
    assert body["geography"] == "NY"


def test_create_seller_requires_price(client):
    payload = seller_payload()
    del payload["selling_price"]
    assert client.post("/sellers", json=payload).status_code == 422


def test_get_seller_404(client):
    assert client.get("/sellers/999").status_code == 404


def test_list_sellers_filter_by_geography(client):
    create_seller(client, name="NY", geography="NY")
    create_seller(client, name="TX", geography="TX")
    resp = client.get("/sellers", params={"geography": "TX"})
    assert [s["name"] for s in resp.json()] == ["TX"]


def test_update_seller_changes_fields(client):
    created = create_seller(client)
    resp = client.put(f"/sellers/{created['id']}", json={"selling_price": 750})
    assert resp.status_code == 200
    assert resp.json()["selling_price"] == 750


def test_delete_seller(client):
    created = create_seller(client)
    assert client.delete(f"/sellers/{created['id']}").status_code == 204
    assert client.get(f"/sellers/{created['id']}").status_code == 404


def test_seller_stats_empty(client):
    assert client.get("/sellers/stats").json() == {"low": None, "high": None, "count": 0}


def test_seller_stats_populated(client):
    create_seller(client, selling_price=300)
    create_seller(client, name="S2", selling_price=900)
    assert client.get("/sellers/stats").json() == {"low": 300, "high": 900, "count": 2}
