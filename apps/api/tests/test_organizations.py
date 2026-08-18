import uuid

from app.organizations.models import Organization


def test_create_and_read_organization(session):
    org = Organization(name="Marlowe Family Law", slug="marlowe-family-law")
    session.add(org)
    session.commit()
    session.refresh(org)

    fetched = session.get(Organization, org.id)
    assert fetched is not None
    assert fetched.name == "Marlowe Family Law"
    assert fetched.slug == "marlowe-family-law"
    assert isinstance(fetched.id, uuid.UUID)  # UUID PK auto-generated
    # timestamps populated by the database on insert
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
