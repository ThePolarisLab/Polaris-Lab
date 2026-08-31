"""Import all SQLAlchemy models so Alembic and runtime share one metadata graph."""

from app.auth.models import (  # noqa: F401
    ProductionAuthBootstrapState,
    ProductionAuthSession,
    ProductionLoginAttempt,
    ProductionPasswordCredential,
)
from app.connectors.outlook_credentials import (  # noqa: F401
    OutlookOAuthCredential,
    OutlookOAuthState,
)
from app.connectors.quickbooks_credentials import (  # noqa: F401
    QuickBooksOAuthCredential,
    QuickBooksOAuthState,
)
from app.identity.models import Identity, OrganizationMembership  # noqa: F401
from app.missions.models import Mission, MissionTask, Workflow  # noqa: F401
from app.models.ace import AceFeedRun, AceImportRun, AceInBondEvent, AceInBondMovement  # noqa: F401
from app.models.company import Company  # noqa: F401
from app.models.financial_snapshot import (  # noqa: F401
    FinancialAccount,
    FinancialSnapshot,
    FinancialSyncHistory,
)
from app.models.fuel import FuelPriceEvidence, FuelPriceImportRun  # noqa: F401
from app.models.memory import MemoryEntry  # noqa: F401
from app.models.motive import (  # noqa: F401
    MotiveCredential,
    MotiveDriverRecord,
    MotiveDriverUtilizationRecord,
    MotiveIftaSummaryRecord,
    MotiveOAuthState,
    MotiveSyncCheckpoint,
    MotiveSyncHistory,
    MotiveVehicleRecord,
    MotiveVehicleUtilizationRecord,
)
from app.models.motive_kpi_snapshot import MotiveVehicleUtilizationKpiSnapshot  # noqa: F401
from app.models.outlook import (  # noqa: F401
    OutlookAttachment,
    OutlookFolder,
    OutlookFolderCheckpoint,
    OutlookMessage,
    OutlookMessageClassification,
    OutlookSyncHistory,
)
from app.models.relationship import KnowledgeRelationship  # noqa: F401
from app.models.team_note import TeamNote  # noqa: F401
from app.models.torqueai import (  # noqa: F401
    TorqueAIDispatch,
    TorqueAIDispatchSyncRun,
    TorqueAIDispatchSyncState,
)
from app.models.truck import Truck  # noqa: F401
from app.organizations.models import Organization  # noqa: F401


def register_models() -> None:
    """Import side effects above register every model with Base.metadata."""

    return None
