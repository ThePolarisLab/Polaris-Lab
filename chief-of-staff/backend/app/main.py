from fastapi import FastAPI

app = FastAPI(title="Polaris Chief of Staff API", version="0.1")

@app.get("/")
def root():
    return {"service": "Polaris Chief of Staff API", "version": "0.1"}

@app.get("/daily-brief")
def daily_brief():
    return {
        "greeting": "Good Morning, Founder",
        "focus": ["Cash flow review", "TEN Leasing follow-up", "CTPAT implementation"],
        "daily_build": "Build Polaris Chief of Staff v0.1 dashboard"
    }

@app.get("/responsibilities")
def responsibilities():
    return [
        {"id": 1, "title": "Finalize TEN Leasing", "priority": "High", "status": "Waiting"},
        {"id": 2, "title": "Review IRS EIN status", "priority": "High", "status": "Active"},
        {"id": 3, "title": "Prepare CTPAT documents", "priority": "Medium", "status": "Active"}
    ]

@app.get("/waiting-on")
def waiting_on():
    return [
        {"id": 1, "title": "IRS EIN update", "contact": "IRS", "waiting_since": "More than 2 weeks"},
        {"id": 2, "title": "TEN Leasing account setup", "contact": "Monish", "waiting_since": "This week"}
    ]
