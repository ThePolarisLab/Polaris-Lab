from app.knowledge.models import BusinessArea, Entity, EntityType

SYSTEMS = (
    Entity(
        id="system.quickbooks",
        name="QuickBooks Online",
        entity_type=EntityType.SYSTEM,
        business_area=BusinessArea.FINANCE,
        default_category="Finance",
        default_priority="High",
        tags=("Accounting", "GST", "Finance"),
        aliases=("QuickBooks", "QBO"),
        related_entities=("mission.q2_compliance",),
    ),
    Entity(
        id="system.motive",
        name="Motive",
        entity_type=EntityType.SYSTEM,
        business_area=BusinessArea.FLEET,
        default_category="Fleet",
        default_priority="High",
        tags=("Mileage", "ELD", "Fleet", "IFTA"),
        aliases=("Motive ELD",),
        related_entities=("mission.q2_compliance",),
    ),
    Entity(
        id="system.hunter_fleet",
        name="Hunter Fleet",
        entity_type=EntityType.SYSTEM,
        business_area=BusinessArea.FLEET,
        default_category="Fleet",
        default_priority="High",
        tags=("Mileage", "Fleet", "IFTA"),
        aliases=("Hunter",),
        related_entities=("mission.q2_compliance",),
    ),
)
