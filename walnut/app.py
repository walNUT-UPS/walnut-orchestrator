from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from walnut.auth.router import auth_router, api_router
from walnut.config import settings
from walnut.database.connection import init_database, close_database

app = FastAPI(
    title="walNUT API",
    description="walNUT - UPS Management Platform with Network UPS Tools (NUT) integration",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(auth_router, prefix="/auth")
app.include_router(api_router, prefix="/api")

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    await init_database()

@app.on_event("shutdown")
async def shutdown_event():
    """Close database on shutdown."""
    await close_database()

@app.get("/")
async def root():
    return {"message": "Welcome to walNUT!"}
