from fastapi import FastAPI

app = FastAPI(
    title="walNUT API",
    description="API for walNUT UPS Management Platform",
    version="1.0.0",
)

from walnut.api import policies, policy_runs, admin_events

app.include_router(policies.router, prefix="/api", tags=["Policies"])
app.include_router(policy_runs.router, prefix="/api", tags=["Policy Runs"])
app.include_router(admin_events.router, prefix="/api/admin", tags=["Admin"]) # Corrected prefix

@app.get("/")
async def root():
    return {"message": "Welcome to walNUT API"}
