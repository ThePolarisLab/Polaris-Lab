"""Import all SQLAlchemy models so Alembic and runtime share one metadata graph."""

from app.connectors.quickbooks_credentials import (  # noqa: F401
    QuickBooksOAuthCredential,
    QuickBooksOAuthState,
)
from app.identity.models import Identity, OrganizationMembership  # noqa: F401
from app.missions.models import Mission, MissionTask, Workflow  # noqa: F401
from app.models.company import Company  # noqa: F401
from app.models.financial_snapshot import (  # noqa: F401
    FinancialAccount,
    FinancialSnapshot,
    FinancialSyncHistory,
)
from app.models.memory import MemoryEntry  # noqa: F401
from app.models.relationship import KnowledgeRelationship  # noqa: F401
from app.models.team_note import TeamNote  # noqa: F401
from app.models.truck import Truck  # noqa: F401
from app.organizations.models import Organization  # noqa: F401


def register_models() -> None:
    """Import side effects above register every model with Base.metadata."""

    return None
