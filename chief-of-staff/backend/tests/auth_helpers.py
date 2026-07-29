from uuid import uuid4

from app.database.database import SessionLocal
from app.identity.models import Identity, OrganizationMembership
from app.organizations.models import Organization
from app.security.providers import LocalTokenProvider


def seed_principal(role: str = "owner", organization_id: str | None = None) -> tuple[dict, dict, dict[str, str]]:
    suffix = uuid4().hex[:10]
    session = SessionLocal()
    try:
        if organization_id is None:
            organization = Organization(slug=f"test-auth-{suffix}", display_name="Test Auth Organization")
            session.add(organization)
            session.flush()
        else:
            organization = session.query(Organization).filter(Organization.id == organization_id).one()

        identity = Identity(email=f"test-auth-{suffix}@example.test", display_name="Test Auth Principal")
        session.add(identity)
        session.flush()

        membership = OrganizationMembership(
            organization_id=organization.id,
            identity_id=identity.id,
            role=role,
        )
        session.add(membership)
        session.commit()
        session.refresh(organization)
        session.refresh(identity)

        token = LocalTokenProvider().issue(identity.id)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Polaris-Organization": organization.id,
        }
        return (
            {"id": organization.id, "slug": organization.slug, "display_name": organization.display_name},
            {"id": identity.id, "email": identity.email, "display_name": identity.display_name},
            headers,
        )
    finally:
        session.close()
