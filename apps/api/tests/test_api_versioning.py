"""The URL contract: feature routes are versioned, infrastructure routes are not."""


def test_organizations_live_under_the_version_prefix(client):
    response = client.post("/api/v1/organizations", json={"name": "Versioned Firm"})

    assert response.status_code == 201


def test_unversioned_organizations_path_is_gone(client):
    """Guards against a feature router being mounted at the root by accident."""
    assert client.get("/organizations").status_code == 404


def test_health_stays_unversioned(client):
    """k8s probes and the Dockerfile point at /health — it must not move."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
