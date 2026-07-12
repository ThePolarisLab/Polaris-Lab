from app.knowledge.models import BusinessArea, EntityType

ENTITY_TYPES = tuple(item.value for item in EntityType)
BUSINESS_AREAS = tuple(item.value for item in BusinessArea)
