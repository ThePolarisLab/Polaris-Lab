from app.knowledge.models import BusinessArea, Entity, EntityType

COMPANIES = (
    Entity(
        id="company.mor_logistics",
        name="MOR Logistics Manitoba Limited",
        entity_type=EntityType.COMPANY,
        business_area=BusinessArea.OPERATIONS,
        default_category="Company",
        default_priority="High",
        tags=("Logistics", "Trucking", "Builder"),
        aliases=("Mor Logistics", "MOR Logistics"),
    ),
    Entity(
        id="company.polaris_labs",
        name="Polaris Labs",
        entity_type=EntityType.COMPANY,
        business_area=BusinessArea.STRATEGY,
        default_category="Company",
        default_priority="High",
        tags=("Polaris", "Builder", "Technology"),
    ),
    Entity(
        id="company.realtime_books",
        name="RealTime Books",
        entity_type=EntityType.COMPANY,
        business_area=BusinessArea.FINANCE,
        default_category="Company",
        default_priority="Medium",
        tags=("Bookkeeping", "Accounting", "Builder"),
        aliases=("Realtime Books",),
    ),
)
