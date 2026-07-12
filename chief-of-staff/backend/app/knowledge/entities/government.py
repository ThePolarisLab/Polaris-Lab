from app.knowledge.models import BusinessArea, Entity, EntityType

GOVERNMENT_ENTITIES = (
    Entity(
        id="government.cra",
        name="Canada Revenue Agency",
        entity_type=EntityType.GOVERNMENT,
        business_area=BusinessArea.FINANCE,
        default_category="Finance",
        default_priority="Critical",
        tags=("CRA", "GST", "Tax", "Government"),
        aliases=("CRA",),
        related_entities=("mission.q2_compliance",),
    ),
    Entity(
        id="government.ifta",
        name="International Fuel Tax Agreement",
        entity_type=EntityType.GOVERNMENT,
        business_area=BusinessArea.COMPLIANCE,
        default_category="Compliance",
        default_priority="Critical",
        tags=("IFTA", "Fuel Tax", "Compliance"),
        aliases=("IFTA",),
        related_entities=("mission.q2_compliance",),
    ),
    Entity(
        id="government.kyu",
        name="Kentucky Weight-Distance Tax",
        entity_type=EntityType.GOVERNMENT,
        business_area=BusinessArea.COMPLIANCE,
        default_category="Compliance",
        default_priority="Critical",
        tags=("KYU", "Kentucky", "Compliance", "Tax"),
        aliases=("KYU",),
        related_entities=("mission.q2_compliance",),
    ),
)
