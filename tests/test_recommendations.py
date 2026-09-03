from tests.conftest import INDUSTRY_PARENT, create_buyer, create_seller


def test_buyer_recommendations_returns_compatible_seller(client):
    buyer = create_buyer(client)
    seller = create_seller(client)
    recs = client.get(f"/buyers/{buyer['id']}/recommendations").json()
    assert [r["id"] for r in recs] == [seller["id"]]
    assert recs[0]["matched_industries"] == [6699]


def test_seller_recommendations_returns_compatible_buyer(client):
    buyer = create_buyer(client)
    seller = create_seller(client)
    recs = client.get(f"/sellers/{seller['id']}/recommendations").json()
    assert [r["id"] for r in recs] == [buyer["id"]]


def test_recommendations_sorted_by_score_desc(client):
    buyer = create_buyer(client)
    # Weak match: one industry. Strong match: two industries.
    create_seller(client, name="Weak", industries=[6699])
    create_seller(client, name="Strong", industries=[6699, 6700])
    recs = client.get(f"/buyers/{buyer['id']}/recommendations").json()
    assert [r["name"] for r in recs] == ["Strong", "Weak"]
    assert recs[0]["score"] >= recs[1]["score"]


def test_recommendations_exclude_inactive(client):
    buyer = create_buyer(client)
    seller = create_seller(client)
    client.put(f"/sellers/{seller['id']}", json={"status": "inactive"})
    assert client.get(f"/buyers/{buyer['id']}/recommendations").json() == []


def test_recommendations_directionality(client):
    # Buyer industry is the child leaf; seller industry is the parent -> no rec.
    buyer = create_buyer(client, industries=[6699])
    create_seller(client, industries=[INDUSTRY_PARENT])
    assert client.get(f"/buyers/{buyer['id']}/recommendations").json() == []


def test_recommendations_404(client):
    assert client.get("/buyers/999/recommendations").status_code == 404
