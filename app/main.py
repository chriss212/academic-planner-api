from fastapi import FastAPI
from app.routers import tasks, availability, plans, ai
from app.routers import constraints

app = FastAPI(
    title="Agente de Planificación Académica",
    version="1.0.0",
    description="API para planificación inteligente con IA generativa"
)

app.include_router(tasks.router)
app.include_router(availability.router)
app.include_router(constraints.router)
app.include_router(plans.router)
app.include_router(ai.router)

@app.get("/health", tags=["status"])
async def health():
    return {"status": "ok"}