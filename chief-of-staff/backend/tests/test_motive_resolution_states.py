from datetime import date
from app.motive.maintenance_readiness import maintenance_readiness_for_trucks

DAY = date(2026, 9, 12)

class C:
    def __init__(self, states): self.states = states
    def _request_json(self, endpoint, *, params, operation):
        if endpoint == "/v1/fault_codes": return {"fault_codes": [], "total": 0}
        rows=[]
        for i,(d,s) in enumerate(self.states):
            rows.append({"inspection_report":{"vehicle":{"number":"M2214"},"date":d,"time":f"{d}T12:00:0{i}Z","inspection_type":"pre_trip","status":"open","is_rejected":False,"odometer":693000+i,"inspected_parts":[{"category":"18 - Lamps/Reflectors","type":"minor","status":s,"defects":[]}]}})
        return {"inspection_reports": rows, "total": len(rows)}

def row(states):
    return maintenance_readiness_for_trucks(truck_numbers=["M2214"],as_of_date=DAY,connector=C(states))["classifications"][0]

def test_resolved_and_reopened_states():
    g=row([("2026-09-10","open"),("2026-09-11","repaired")])["inspection_resolution_groups"][0]
    assert g["resolution_state"] == "resolved"
    assert g["resolution_confirmed"] is True
    reopened=row([("2026-09-09","open"),("2026-09-10","repaired"),("2026-09-12","open")])
    g=reopened["inspection_resolution_groups"][0]
    assert g["resolution_state"] == "reopened"
    assert g["reopened_confirmed"] is True
    assert reopened["classification"] == "verify"

def test_non_explicit_states_do_not_prove_resolution():
    g=row([("2026-09-10","open"),("2026-09-11","good")])["inspection_resolution_groups"][0]
    assert g["resolution_state"] == "observed_non_open"
    assert g["good_status_proves_repair"] is False
    g=row([("2026-09-09","repaired"),("2026-09-11","open")])["inspection_resolution_groups"][0]
    assert g["resolution_state"] == "open"
    assert g["explicit_resolution_status"] is None
    assert g["disappearance_means_resolved"] is False
