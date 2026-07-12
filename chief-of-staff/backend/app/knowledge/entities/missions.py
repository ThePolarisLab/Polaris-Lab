from app.knowledge.models import BusinessArea, Entity, EntityType

MISSIONS = (
    Entity(
        id="mission.q2_compliance",
        name="Complete Q2 Compliance",
        entity_type=EntityType.MISSION,
        business_area=BusinessArea.COMPLIANCE,
        default_category="Compliance",
        default_priority="Critical",
        tags=("Q2", "IFTA", "GST", "KYU", "Mission"),
        aliases=("Q2 Compliance", "Complete Q2", "Finish Q2"),
        related_entities=(
            "vendor.eco_petroleum",
            "vendor.bvd_petroleum",
            "system.quickbooks",
            "system.motive",
            "system.hunter_fleet",
            "government.cra",
            "government.ifta",
            "government.kyu",
        ),
    ),
)
