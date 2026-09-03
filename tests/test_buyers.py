from tests.conftest import buyer_payload, create_buyer


def test_create_buyer_returns_object_with_id(client):
    body = create_buyer(client)
    assert body["id"] == 1
    assert body["status"] == "active"
    assert body["name"] == "Acme Capital"


def test_ids_are_monotonic(client):
    first = create_buyer(client)
    second = create_buyer(client, name="Second")
    assert second["id"] == first["id"] + 1


def test_create_buyer_rejects_inverted_limits(client):
    resp = client.post("/buyers", json=buyer_payload(lower_limit=1000, upper_limit=100))
    assert resp.status_code == 422


def test_create_buyer_requires_industries(client):
    resp = client.post("/buyers", json=buyer_payload(industries=[]))
    assert resp.status_code == 422


def test_get_buyer_404(client):
    assert client.get("/buyers/999").status_code == 404


def test_get_buyer(client):
    created = create_buyer(client)
    resp = client.get(f"/buyers/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_list_buyers_pagination(client):
    for i in range(3):
        create_buyer(client, name=f"B{i}")
    resp = client.get("/buyers", params={"limit": 2, "offset": 0})
    assert len(resp.json()) == 2
    resp = client.get("/buyers", params={"limit": 2, "offset": 2})
    assert len(resp.json()) == 1


def test_list_buyers_filter_by_geography(client):
    create_buyer(client, name="NY buyer", geographies=["NY"])
    create_buyer(client, name="CA buyer", geographies=["CA"])
    resp = client.get("/buyers", params={"geography": "CA"})
    names = [b["name"] for b in resp.json()]
    assert names == ["CA buyer"]


def test_update_buyer_changes_fields(client):
    created = create_buyer(client)
    resp = client.put(f"/buyers/{created['id']}", json={"upper_limit": 5000})
    assert resp.status_code == 200
    assert resp.json()["upper_limit"] == 5000
    # untouched field preserved
    assert resp.json()["lower_limit"] == 100


def test_update_buyer_404(client):
    assert client.put("/buyers/999", json={"name": "x"}).status_code == 404


def test_delete_buyer(client):
    created = create_buyer(client)
    assert client.delete(f"/buyers/{created['id']}").status_code == 204
    assert client.get(f"/buyers/{created['id']}").status_code == 404


def test_buyer_stats_empty(client):
    resp = client.get("/buyers/stats")
    assert resp.json() == {"low": None, "high": None, "count": 0}


def test_buyer_stats_populated(client):
    create_buyer(client, lower_limit=50, upper_limit=200)
    create_buyer(client, name="B2", lower_limit=10, upper_limit=999)
    resp = client.get("/buyers/stats")
    assert resp.json() == {"low": 10, "high": 999, "count": 2}
