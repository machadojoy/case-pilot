"""Tests for GET /api/v1/organizations — the paginated list endpoint."""

LIST_URL = "/api/v1/organizations"


def _create(client, name: str) -> dict:
    return client.post(LIST_URL, json={"name": name}).json()


def test_list_is_empty_initially(client):
    response = client.get(LIST_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["offset"] == 0
    assert body["limit"] == 20  # default


def test_list_returns_created_organizations(client):
    _create(client, "Alpha Legal")
    _create(client, "Beta Legal")

    body = client.get(LIST_URL).json()

    assert body["total"] == 2
    assert {item["slug"] for item in body["items"]} == {"alpha-legal", "beta-legal"}


def test_pagination_slices_and_total_counts_everything(client):
    for index in range(5):
        _create(client, f"Firm {index}")

    first = client.get(LIST_URL, params={"offset": 0, "limit": 2}).json()
    second = client.get(LIST_URL, params={"offset": 2, "limit": 2}).json()
    third = client.get(LIST_URL, params={"offset": 4, "limit": 2}).json()

    assert [len(page["items"]) for page in (first, second, third)] == [2, 2, 1]
    # total is the full count, not the page size
    assert first["total"] == second["total"] == third["total"] == 5
    assert second["offset"] == 2
    assert second["limit"] == 2


def test_pages_do_not_overlap_or_skip(client):
    for index in range(6):
        _create(client, f"Firm {index}")

    seen = []
    for offset in (0, 2, 4):
        page = client.get(LIST_URL, params={"offset": offset, "limit": 2}).json()
        seen.extend(item["id"] for item in page["items"])

    assert len(seen) == 6
    assert len(set(seen)) == 6  # deterministic ordering: no duplicates, nothing missed


def test_offset_beyond_the_end_returns_an_empty_page(client):
    _create(client, "Only Firm")

    body = client.get(LIST_URL, params={"offset": 50}).json()

    assert body["items"] == []
    assert body["total"] == 1


def test_limit_bounds_are_enforced(client):
    assert client.get(LIST_URL, params={"limit": 0}).status_code == 422
    assert client.get(LIST_URL, params={"limit": 101}).status_code == 422
    assert client.get(LIST_URL, params={"offset": -1}).status_code == 422
