"""ForexSlave Dashboard Backend — FastAPI application.

Provides REST API to:
- Read/write trading config (sessions, grid policy, risk controls)
- Read live status (positions, event risk, bridge state)
- Trigger actions (force refresh, force close, toggle trading)

Runs on localhost:8081 by default.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.config import router as config_router
from routes.status import router as status_router
from routes.actions import router as actions_router

app = FastAPI(
    title="ForexSlave Dashboard",
    description="REST API for managing the ForexSlave trading system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # localhost-only in practice
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config_router, prefix="/api/config", tags=["config"])
app.include_router(status_router, prefix="/api/status", tags=["status"])
app.include_router(actions_router, prefix="/api/actions", tags=["actions"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}