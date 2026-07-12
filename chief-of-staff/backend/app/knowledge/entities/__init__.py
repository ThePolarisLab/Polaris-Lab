from app.knowledge.entities.companies import COMPANIES
from app.knowledge.entities.government import GOVERNMENT_ENTITIES
from app.knowledge.entities.missions import MISSIONS
from app.knowledge.entities.systems import SYSTEMS
from app.knowledge.entities.vendors import VENDORS

ALL_ENTITIES = (*COMPANIES, *VENDORS, *SYSTEMS, *GOVERNMENT_ENTITIES, *MISSIONS)
