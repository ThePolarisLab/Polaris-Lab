"""Read-only Motive maintenance readiness advisory."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Any
from app.connectors.motive import MotiveConnector, MotiveConnectorError
LOOKBACK_DAYS=7
PAGE_SIZE=100
MAX_PAGES=20
MAX_WINDOW_ROWS=PAGE_SIZE*MAX_PAGES

def maintenance_readiness_for_trucks(*,truck_numbers:list[str],as_of_date:date,connector:MotiveConnector)->dict[str,Any]:
    wanted={n.strip().casefold():n.strip() for n in truck_numbers if n and n.strip()}
    if not wanted:return _empty_result(as_of_date)
    start=as_of_date-timedelta(days=LOOKBACK_DAYS-1)
    faults,fa,fc=_read_all_pages(connector,"/v1/fault_codes",{"start_date":start.isoformat(),"end_date":as_of_date.isoformat()},"assignment_maintenance_fault_codes",collection="fault_codes")
    reports,ra,rc=_read_all_pages(connector,"/v2/inspection_reports",{"updated_after":start.isoformat(),"entity_type":"vehicle"},"assignment_maintenance_inspection_reports",collection="inspection_reports")
    data={k:{"truck_number":v,"opened_fault_count":0,"rejected_inspection_count":0,"open_inspection_part_count":0} for k,v in wanted.items()}
    if fa:
        for fault in _children(faults,"fault_codes","fault_code"):
            vehicle=fault.get("vehicle") if isinstance(fault.get("vehicle"),dict) else {}
            item=data.get(str(vehicle.get("number") or "").strip().casefold())
            if item is not None and _norm(fault.get("status"))=="opened":item["opened_fault_count"]+=1
    if ra:
        for report in _children(reports,"inspection_reports","inspection_report"):
            vehicle=report.get("vehicle") if isinstance(report.get("vehicle"),dict) else {}
            item=data.get(str(vehicle.get("number") or "").strip().casefold())
            if item is None:continue
            if report.get("is_rejected") is True:item["rejected_inspection_count"]+=1
            parts=report.get("inspected_parts") if isinstance(report.get("inspected_parts"),list) else []
            for part in parts:
                if isinstance(part,dict) and _norm(part.get("status"))=="open":item["open_inspection_part_count"]+=1
    results=[]
    for key in wanted:
        item=data[key]; blockers=[]; reasons=[]
        if item["rejected_inspection_count"]:blockers.append("inspection_report_rejected")
        if not fa:reasons.append("fault_code_data_unavailable")
        elif not fc:reasons.append("fault_code_result_window_incomplete")
        elif item["opened_fault_count"]:reasons.append("opened_fault_code_present")
        if not ra:reasons.append("inspection_data_unavailable")
        elif not rc:reasons.append("inspection_result_window_incomplete")
        elif item["open_inspection_part_count"]:reasons.append("open_inspection_part_present")
        classification="not_suitable" if blockers else "verify" if reasons else "clear"
        results.append({**item,"classification":classification,"hard_blockers":blockers,"verification_reasons":reasons,"advisory_only":True,"dispatcher_approval_required":True,"provider_window_days":LOOKBACK_DAYS})
    return {"as_of_date":as_of_date.isoformat(),"fault_codes_available":fa,"fault_codes_window_complete":fc,"inspection_reports_available":ra,"inspection_reports_window_complete":rc,"classifications":results,"provider_writes_performed":False,"dispatch_mutation_performed":False,"autonomous_assignment_performed":False}

def _empty_result(as_of_date:date)->dict[str,Any]:
    return {"as_of_date":as_of_date.isoformat(),"fault_codes_available":None,"fault_codes_window_complete":None,"inspection_reports_available":None,"inspection_reports_window_complete":None,"classifications":[],"provider_writes_performed":False,"dispatch_mutation_performed":False,"autonomous_assignment_performed":False}

def _read_all_pages(connector:MotiveConnector,endpoint:str,base_params:dict[str,Any],operation:str,*,collection:str)->tuple[dict[str,Any],bool,bool]:
    combined=[]; expected_total=None
    for page_no in range(1,MAX_PAGES+1):
        params={**base_params,"per_page":PAGE_SIZE,"page_no":page_no}
        try:payload=connector._request_json(endpoint,params=params,operation=operation)
        except MotiveConnectorError:return {collection:combined},False,False
        if not isinstance(payload,dict):return {collection:combined},False,False
        rows=payload.get(collection); total=payload.get("total")
        if not isinstance(rows,list) or not isinstance(total,int) or total<0:return {collection:combined},True,False
        if expected_total is None:
            expected_total=total
            if expected_total>MAX_WINDOW_ROWS:return {collection:combined+rows,"total":expected_total},True,False
        elif total!=expected_total:return {collection:combined+rows,"total":expected_total},True,False
        combined.extend(rows)
        if len(combined)>=expected_total:return {collection:combined[:expected_total],"total":expected_total},True,True
        if not rows:return {collection:combined,"total":expected_total},True,False
    return {collection:combined,"total":expected_total},True,False

def _children(payload:dict[str,Any],collection:str,child:str)->list[dict[str,Any]]:
    rows=payload.get(collection)
    if not isinstance(rows,list):return []
    return [row[child] for row in rows if isinstance(row,dict) and isinstance(row.get(child),dict)]

def _norm(value:Any)->str:return str(value or "").strip().casefold()
