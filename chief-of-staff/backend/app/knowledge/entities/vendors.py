from app.knowledge.models import BusinessArea, Entity, EntityType

VENDORS = (
    Entity(
        id="vendor.eco_petroleum",
        name="Eco Petroleum",
        entity_type=EntityType.VENDOR,
        business_area=BusinessArea.COMPLIANCE,
        default_category="Compliance",
        default_priority="High",
        tags=("Fuel", "Vendor", "IFTA"),
        aliases=("Eco Fuel",),
        systems=("Fuel Reports",),
        related_entities=("mission.q2_compliance",),
    ),
    Entity(
        id="vendor.bvd_petroleum",
        name="BVD Petroleum",
        entity_type=EntityType.VENDOR,
        business_area=BusinessArea.COMPLIANCE,
        default_category="Compliance",
        default_priority="High",
        tags=("Fuel", "Vendor", "IFTA"),
        aliases=("BVD", "BVD Fuel"),
        systems=("Fuel Reports",),
        related_entities=("mission.q2_compliance",),
    ),
    Entity(
        id="vendor.jd_factors",
        name="JD Factors",
        entity_type=EntityType.VENDOR,
        business_area=BusinessArea.FINANCE,
        default_category="Finance",
        default_priority="High",
        tags=("Factoring", "Accounts Receivable", "Vendor"),
        aliases=("JD Factor",),
    ),
)
