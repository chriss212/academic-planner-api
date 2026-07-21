from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ModelCostBreakdown(BaseModel):
    modelo: str
    llamadas: int
    tokens_entrada: int
    tokens_salida: int
    costo_entrada_usd: float
    costo_salida_usd: float
    costo_total_usd: float


class CostEstimateOut(BaseModel):
    """Estimación de coste operativo del agente"""

    modelo_configurado: str
    precio_entrada_usd_por_1m: float
    precio_salida_usd_por_1m: float

    total_llamadas: int
    llamadas_con_tokens: int
    tokens_entrada: int
    tokens_salida: int
    tokens_totales: int

    costo_total_usd: float
    costo_promedio_por_llamada_usd: Optional[float] = None
    costo_estimado_mensual_usd: Optional[float] = None

    desglose_por_modelo: list[ModelCostBreakdown] = []
