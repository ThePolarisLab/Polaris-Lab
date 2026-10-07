# Polaris Fuel Intelligence Constitution

Status: **CONFIRMED MOR operating baseline / CURRENT manual procedure / FUTURE automation**.
Recorded: 2026-10-06. Authority: MOR management instructions supplied by Surinder for this specification. This document establishes a permanent operating domain; it does not authorize implementation or certify production automation.

## Purpose and governing principle

Fuel Intelligence is a core Polaris operating domain affecting dispatch, lane pricing, load profitability, truckwise and company P&L, driver productivity, HOS utilization, maintenance analysis, abnormal-fueling detection and fleet buy/keep/repair/replace/sell decisions.

> Buy the right amount of fuel, at the right place, at the right time, using the right supplier, while minimizing total trip operating cost and generating reliable data for better business decisions.

This domain specification follows the [Polaris Constitution](../governance/POLARIS_CONSTITUTION.md) and [Engineering Principles](../governance/ENGINEERING_PRINCIPLES.md). The [canonical project state](../../PROJECT_STATE.md) remains the authority for implemented and certified capabilities. Approved business intent is distinct from deployed capability.

## 1. MOR-confirmed operating rules

- Optimize total trip operating cost, rather than pump price alone.
- Normally start planning around **25% fuel remaining**, subject to safety and trip conditions. This is a planning trigger, not a universal minimum safe reserve.
- Prefer full fills/full-to-full fueling where practical, particularly when prices are similar.
- An unnecessary additional stop typically consumes **45–50 minutes**, plus detour, idling and productivity impact. Use approximately **$30–$40** practical all-in stop cost unless better trip-specific evidence is available. Record the cost currency and assumptions; management must confirm the applicable currency before cross-currency comparisons.
- Reject a partial fill followed by a cheaper stop when savings are only a few dollars and do not materially exceed the additional stop cost. Do not double-count time/idle/detour already included in an all-in estimate.
- Where practical, align fueling with the required 30-minute U.S. HOS break, end-of-shift stop, meal/rest stop or another unavoidable stop. Validate duty status and applicable HOS requirements; fueling does not by itself establish a qualifying break.
- Compare BVD-only, Eco-only and combined BVD + Eco scenarios where reliable applicable rates exist. Mark unsupported scenarios unavailable rather than inventing prices.
- Safety overrides optimization: if the planned station cannot safely be reached, use the next reasonable safe truck stop and record the exception.

### Current station defaults — subject to management change

| Station/area | Current MOR default |
| --- | --- |
| Grand Forks | Full |
| Tonkawa | Full |
| Pearsall | Full |
| Belton | Mandatory full |
| Matthews | Mandatory full |
| Napoleon | Mandatory full |
| GTA / Brampton / Mississauga | Evaluate |
| North Bay | Conditional |
| Nipigon | Small top-up only where needed |
| Laredo | Generally avoid unnecessary fueling unless operationally required |

These are management-changeable defaults, not immutable rules or exact station identifiers. Mandatory full remains subject to physical capacity and safety. Tonkawa has historically been preferred over Oklahoma City partly for bypass, congestion and driver convenience. Confirm the exact approved station, accessibility and supplier before issuing a plan.

## 2. Current manual fuel-planning workflow

This is the management-described current procedure, not a claim of independently observed clicks or an automated service.

| Step | Manual action and required check |
| --- | --- |
| 1 | Identify the dispatched load in TorqueAI; confirm load identity and route. |
| 2 | Confirm assigned truck and driver against the dispatch. |
| 3 | Check current/latest reliable truck fuel level; retain its source and timestamp. |
| 4 | Review historical average, recent and same-lane MPG where available; identify the basis used. |
| 5 | Read Motive available drive time, shift time, cycle hours, next required break, expected end of shift and current location; verify freshness and driver/truck match. |
| 6 | Retrieve BVD/Eco rate files from Outlook applicable to the specific fueling/trip date. Do not substitute an older day/week when a current applicable file exists. Verify effective dates, supplier, station, product, currency and rate basis. |
| 7 | Select MOR-approved/default route stations; check exact location, accessibility and spacing. |
| 8 | Calculate expected gallons = route miles / expected MPG; adjust purchase quantity for onboard fuel, tank capacity, safe reserve, spacing, route conditions and HOS. |
| 9 | Normalize CAD/USD and litres/U.S. gallons explicitly. Preserve original values; use a documented dated FX basis when currency conversion is required. |
| 10 | Compare BVD-only, Eco-only and combined plans using supported evidence; disclose unavailable alternatives. |
| 11 | Compare total economics: fuel price, incremental stop cost, detour, congestion, idle time, driver time and HOS impact. |
| 12 | Prefer fueling overlapping an unavoidable/HOS stop where practical; validate the actual duty-status treatment. |
| 13 | Confirm reachable stations, reserve, capacity and safe execution before finalizing. |
| 14 | Dispatcher sends a concise operational plan to the driver with station/supplier, quantity or full-fill instruction, timing, reserve and safety fallback. |
| 15 | After the trip, reconcile planned versus actual purchases and supplier charges; retain unresolved variances for review. |

Unknown/stale fuel, HOS, location, tank capacity or conflicting assignment prevents a reliable final plan until clarified. Missing rates prevent claiming a cheapest supported scenario; dispatcher may approve a documented safe fallback. Material discrepancies go to management/accounting. Safety requires immediate operational fallback rather than waiting for price evidence.

### Required planning and reconciliation data — where available

| Group | Fields |
| --- | --- |
| Load and route | Load number, customer, pickup/delivery, route, loaded miles, expected empty miles, commodity, weight, temperature instructions |
| Vehicle | Truck/unit, make/model/year, tank capacity, current fuel, current location, odometer |
| Driver and efficiency | Driver, driver HOS, historical/recent/same-lane MPG |
| Purchase | Supplier, station, date/time, gallons/litres, fuel card reference kept private/masked |
| Price and billing | Posted/retail price, MOR contracted/net price, tax, fees, currency, invoice/reference, supplier transaction ID |

Retain source identity, observation/effective timestamps, units, comparison basis and missing-data flags for each input. Fields not returned by a source remain unknown. This is a required target information inventory, not a claim every connector currently provides it. Use miles per U.S. gallon for the MPG formula; 1 U.S. gallon = 3.785411784 litres. Quantities and unit prices must be converted consistently; CAD and USD cannot be compared directly. Do not invent FX rates or recompute provider-authored totals as replacement evidence.

### Reconciliation and exception analysis

Distinguish **what MOR actually bought** from **what the supplier charged MOR**. Preserve purchase/receipt/transaction facts and invoice facts separately; correlate identities, product, quantity, station, timestamp, units, taxes/fees and effective contracted price before calculating a difference. Flag material discrepancies for management/accounting; a technical difference is not proof of supplier liability or an accounting adjustment.

Review actual fuel materially above plan, unplanned stops, high-cost unplanned fueling, fueling outside the approved plan, duplicate fueling, quantity mismatch, price mismatch, abnormal MPG, excessive idling and unexplained use. Correlate Motive, route, load, weather, maintenance, dispatch instructions and HOS. Fuel data alone is not proof of driver misconduct.

Keep these evidence layers distinct:

1. **Observed fact:** attributable source value.
2. **Calculated fact:** reproducible calculation with inputs, units and assumptions.
3. **Variance:** difference on a stated comparable basis.
4. **Possible explanation:** hypothesis requiring investigation.
5. **Confirmed cause:** conclusion supported by evidence and accountable review.

Human acceptance of a discrepancy does not overwrite its technical result. Follow the existing [Fuel Review discrepancy treatment](../engineering/FUEL_REVIEW_DISCREPANCY_TREATMENT.md) for append-only review events and accounting boundaries. Materiality thresholds remain a management decision; the existing precision-review band is not a universal operating tolerance.

### Business decision outputs

Fuel Intelligence must inform lane costing, rate quoting, load/lane/truckwise/company P&L, maintenance investigation, abnormal-fueling detection, driver/truck efficiency and fleet buy/keep/repair/replace/sell decisions. These are intended uses, not certification of complete profitability reporting.

Because MOR operates recurring/similar lanes, compare trucks on the same or similar lanes alongside standalone history. Explain differences in load/weight, route, empty miles, weather, traffic, idling, HOS, equipment and data coverage; disclose normalization assumptions before ranking trucks.

`Expected fuel gallons = expected route miles / expected truck MPG`

`Expected fuel cost = expected gallons × expected MOR fuel price along the planned route`

Use quantity-weighted route pricing or sum station quantity × comparable station price where appropriate. Fuel is one component of full lane economics: driver, tractor/trailer, maintenance reserve, tolls, border cost, insurance allocation, empty miles and desired margin. State mile denominators and avoid counting empty miles twice. Do not equate purchased fuel with fuel consumed on a load without an allocation basis and opening/closing onboard fuel.

The target system should answer: today's best truck/load fuel plan; why one truck used more than another on a comparable lane; lowest normalized truck fuel cost; load fuel variance; real lane cost per mile; customer quote; losing trucks; repair/keep/replace/sell options; and estimated replacement-tractor savings. Answers must expose coverage, assumptions and uncertainty. Fleet recommendations require broader economic evidence and management decisions.

## 3. Future/proposed automation — NOT YET FULLY AUTONOMOUS

The following end-to-end workflow is a target specification, not an implemented or production-certified service:

TorqueAI dispatch sent → Polaris trigger → collect load/route/truck/driver → collect Motive HOS/location/vehicle information → obtain current applicable BVD/Eco rates where reliable integration exists → obtain historical/same-lane MPG → calculate requirement → calculate BVD-only/Eco-only/combined plans → evaluate total cost/HOS/safety/reserve → recommend → initially require dispatcher validation → deliver the approved concise driver plan → monitor supported material deviations → reconcile post-trip supplier transactions → update profitability and fleet analytics.

### Existing capability boundaries and integration gates

- TorqueAI durable dispatch ingestion and bounded Motive location/utilization/KPI feeds are recorded in PROJECT_STATE. They do not prove a dispatch-sent planning trigger, complete driver HOS access or automatic driver-plan delivery.
- Representative BVD CAD, Eco CAD and Eco USD invoice ingestion/replay evidence exists. Fuel comparison is bounded; manual imports and scheduled/skipped feeds do not establish fresh rates or unattended planning.
- BVD transaction API capability/documentation and official CAD/USD PCN information have been identified. Production transaction credentials, authentication and contract acceptance must be verified before enabling access; do not assume configured credentials. The [BVD contract](../engineering/BVD_FUEL_CONNECTOR_V1_CONTRACT.md) preserves provider-specific gates.
- Eco price/invoice file import paths exist, including [selected historical price import](../engineering/ECO_SELECTED_PRICE_IMPORT.md). Eco API/feed availability and method still require verification; file support does not prove API availability or automatic current-rate access.
- General driver-plan delivery, trip MPG completeness, end-to-end automated reconciliation/P&L and fleet decision automation are not certified by this specification.

Implementation must use the canonical tenant-bound Python connector runtime, Neon durable evidence and existing ownership boundaries; do not create a second token owner or rely on disposable Render files. Each stage needs explicit contracts, tests, bounded permissions, live acceptance and freshness evidence before changing its status.

### Proposed agent contract and handoffs

| Item | Target requirement |
| --- | --- |
| Agent | Polaris Fuel Intelligence, advisory within management-approved scope |
| Inputs/tools | Governed TorqueAI reads, certified Motive fields, approved Outlook/provider rate evidence, MPG history, approved stations, route evidence and supplier purchase/invoice evidence |
| Trigger | Proposed dispatch-sent event; current manual trigger around 25% fuel or operational need |
| Decisions | Comparable three-supplier scenarios; total-cost choice; safe reserve/capacity/reachability; explicit unavailable scenarios and fallbacks |
| Validation | Source freshness/date, tenant/load/driver/truck identity, positive supported MPG, units/currency, tax/fee basis, station identity, HOS and safety feasibility |
| Allowed output | Calculations, comparisons, explained recommendation, prepared driver instructions and tracked exceptions |
| Human gate | Dispatcher validates initial plans and approved communication; management/accounting reviews material variances and consequential decisions |
| Audit | Source IDs/timestamps, originals and normalized values, policy/version, assumptions, alternatives/costs, approval identity/time, instruction version/delivery evidence, deviations and review disposition |
| Handoffs | Dispatch supplies assignment; fuel agent prepares recommendation; dispatcher approves communication; reconciliation supplies attributed variance; costing/fleet analytics consume reviewed facts |
| Completion | Approved plan and recorded communication for planning; separately, post-trip reconciliation with resolved or explicitly assigned open exceptions. Delivery and reconciliation must not be inferred from draft generation. |

Before implementation, obtain management decisions on reserve policies per truck/route, station identities, stop-cost currency/calibration, materiality thresholds, MPG windows/normalization, FX/tax treatment, freshness limits, fallback and escalation owners, driver communication channel/acknowledgment, monitoring scope and stage-specific acceptance criteria. Verify HOS field availability, provider contracts/credentials and source coverage through additional live training and certification.

## 4. Governance, safety and authority limits

Within approved authority, Polaris may calculate, compare, recommend, flag, explain, prepare instructions and track exceptions. This specification does not grant production write permissions or authorize autonomous communication.

Until explicit MOR management approval, Polaris must not autonomously cancel fuel cards, change card limits, block drivers, modify supplier accounts, authorize supplier payments, change supplier settings, accuse drivers of misuse or make irreversible fleet decisions. Recommendations remain explainable and challengeable. Source evidence and historical approval events must not be silently overwritten.

Never put API keys, full fuel-card numbers, supplier credentials, account numbers, confidential live rate files or other secrets in GitHub. Store authorized private evidence and credentials through existing tenant-scoped governed storage/secret mechanisms; public documents use sanitized references only.

Management owns operating defaults and authority changes. Record approved changes with approver, effective date, rationale and version; preserve previous policy for replay of historical decisions. A document change is not a deployment, a connector configuration is not fresh evidence, and a passing test is not production certification.
