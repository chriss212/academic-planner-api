from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import tasks, availability, plans, ai, auth
from app.routers import constraints
from app.core.config import settings

app = FastAPI(
    title="Agente de Planificación Académica",
    version="1.0.0",
    description="API para planificación inteligente con IA generativa"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(availability.router)
app.include_router(constraints.router)
app.include_router(plans.router)
app.include_router(ai.router)

@app.get("/health", tags=["status"])
async def health():
    return {"status": "ok"}