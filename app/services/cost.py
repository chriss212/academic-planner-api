"""Estimación de coste operativo del agente"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ai_trace import AITrace
from app.schemas.cost import CostEstimateOut, ModelCostBreakdown


def _round(value: float) -> float:
    # 6 decimales: los costes por llamada de gpt-4o-mini rondan fracciones de céntimo.
    return round(value, 6)


async def estimate_cost(
    db: AsyncSession,
    user_id: UUID,
    monthly_plans: int | None = None,
) -> CostEstimateOut:
    price_in = settings.openai_price_input_per_1m
    price_out = settings.openai_price_output_per_1m

    total_calls = await db.scalar(
        select(func.count(AITrace.id)).where(AITrace.user_id == user_id)
    )

    rows = (
        await db.execute(
            select(
                AITrace.modelo_usado,
                func.count(AITrace.id),
                func.coalesce(func.sum(AITrace.tokens_entrada), 0),
                func.coalesce(func.sum(AITrace.tokens_salida), 0),
                func.count(AITrace.tokens_entrada),
            )
            .where(AITrace.user_id == user_id)
            .group_by(AITrace.modelo_usado)
        )
    ).all()

    desglose: list[ModelCostBreakdown] = []
    tokens_in = tokens_out = calls_with_tokens = 0
    total_cost = 0.0

    for modelo, llamadas, sum_in, sum_out, con_tokens in rows:
        cost_in = sum_in / 1_000_000 * price_in
        cost_out = sum_out / 1_000_000 * price_out
        desglose.append(
            ModelCostBreakdown(
                modelo=modelo,
                llamadas=llamadas,
                tokens_entrada=sum_in,
                tokens_salida=sum_out,
                costo_entrada_usd=_round(cost_in),
                costo_salida_usd=_round(cost_out),
                costo_total_usd=_round(cost_in + cost_out),
            )
        )
        tokens_in += sum_in
        tokens_out += sum_out
        calls_with_tokens += con_tokens
        total_cost += cost_in + cost_out

    avg_per_call = total_cost / calls_with_tokens if calls_with_tokens else None
    monthly = avg_per_call * monthly_plans if (avg_per_call is not None and monthly_plans) else None

    return CostEstimateOut(
        modelo_configurado=settings.openai_model,
        precio_entrada_usd_por_1m=price_in,
        precio_salida_usd_por_1m=price_out,
        total_llamadas=total_calls or 0,
        llamadas_con_tokens=calls_with_tokens,
        tokens_entrada=tokens_in,
        tokens_salida=tokens_out,
        tokens_totales=tokens_in + tokens_out,
        costo_total_usd=_round(total_cost),
        costo_promedio_por_llamada_usd=_round(avg_per_call) if avg_per_call is not None else None,
        costo_estimado_mensual_usd=_round(monthly) if monthly is not None else None,
        desglose_por_modelo=desglose,
    )
