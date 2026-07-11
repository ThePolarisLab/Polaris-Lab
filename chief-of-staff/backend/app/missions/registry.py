MISSION_REGISTRY = {
    "q2_compliance": {
        "title": "Complete Q2 Compliance",
        "description": "Collect fuel and mileage data, calculate and file IFTA, file GST/HST and KYU, and archive confirmations.",
        "priority": "Critical",
        "workflows": [
            {"title": "Fuel Collection", "tasks": [
                {"title": "Retrieve Eco Petroleum fuel report", "system": "Eco Petroleum", "capability": "Compliance"},
                {"title": "Retrieve BVD Petroleum fuel report", "system": "BVD Petroleum", "capability": "Compliance"},
            ]},
            {"title": "Mileage Collection", "tasks": [
                {"title": "Retrieve Motive mileage by province and state", "system": "Motive", "capability": "Fleet"},
                {"title": "Retrieve Hunter Fleet mileage by province and state", "system": "Hunter Fleet", "capability": "Fleet"},
            ]},
            {"title": "Tax Calculation", "tasks": [
                {"title": "Reconcile total fuel and mileage", "system": "Polaris", "capability": "Compliance"},
                {"title": "Calculate IFTA by province and state", "system": "Polaris", "capability": "Compliance"},
                {"title": "Prepare GST/HST return from QuickBooks", "system": "QuickBooks Online", "capability": "Finance"},
            ]},
            {"title": "Government Filing", "tasks": [
                {"title": "File IFTA return", "system": "Tax Portal", "capability": "Compliance"},
                {"title": "File GST/HST return", "system": "CRA", "capability": "Finance"},
                {"title": "File KYU return", "system": "Kentucky Tax Portal", "capability": "Compliance"},
                {"title": "Archive reports and confirmation numbers", "system": "Polaris Memory", "capability": "Memory"},
            ]},
        ],
    }
}

def get_template(template_key: str) -> dict | None:
    return MISSION_REGISTRY.get(template_key)
