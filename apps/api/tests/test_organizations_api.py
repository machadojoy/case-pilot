import uuid

from app.organizations import service

URL = "/api/v1/organizations"


def test_create_organization(client):
    response = client.post(URL, json={"name": "Marlowe Family Law"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Marlowe Family Law"
    assert body["slug"] == "marlowe-family-law"  # derived server-side
    assert uuid.UUID(body["id"])  # valid UUID PK
    assert body["created_at"] is not None


def test_create_organization_slugifies_accents(client):
    response = client.post(URL, json={"name": "Müller & Associés"})

    assert response.status_code == 201
    assert response.json()["slug"] == "muller-associes"


def test_duplicate_name_gets_a_suffixed_slug(client):
    first = client.post(URL, json={"name": "Acme Legal"})
    second = client.post(URL, json={"name": "Acme Legal"})

    assert first.json()["slug"] == "acme-legal"
    assert second.status_code == 201
    assert second.json()["slug"] == "acme-legal-2"


def test_slug_exhaustion_returns_409(client, monkeypatch):
    """When every candidate slug is taken, the retry loop gives up with a 409."""
    monkeypatch.setattr(service, "MAX_SLUG_ATTEMPTS", 1)  # only the bare slug is tried
    client.post(URL, json={"name": "Acme Legal"})

    response = client.post(URL, json={"name": "Acme Legal"})

    assert response.status_code == 409


def test_create_organization_rejects_empty_name(client):
    response = client.post(URL, json={"name": ""})

    assert response.status_code == 422


def test_create_organization_rejects_overlong_name(client):
    response = client.post(URL, json={"name": "x" * 201})

    assert response.status_code == 422


def test_get_organization(client):
    created = client.post(URL, json={"name": "Marlowe Family Law"}).json()

    response = client.get(f"{URL}/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["slug"] == "marlowe-family-law"


def test_get_unknown_organization_returns_404(client):
    response = client.get(f"{URL}/{uuid.uuid4()}")

    assert response.status_code == 404
