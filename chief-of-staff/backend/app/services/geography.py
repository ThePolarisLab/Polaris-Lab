"""Exact Canadian province aliases; no fuzzy location matching."""
PROVINCES = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba",
    "NB": "New Brunswick", "NL": "Newfoundland and Labrador", "NS": "Nova Scotia",
    "NT": "Northwest Territories", "NU": "Nunavut", "ON": "Ontario",
    "PE": "Prince Edward Island", "QC": "Quebec", "SK": "Saskatchewan", "YT": "Yukon",
}


def province_values(value):
    for code, name in PROVINCES.items():
        if value.casefold() in (code.casefold(), name.casefold()):
            return (code, name)
    raise ValueError("INVALID_PROVINCE")
