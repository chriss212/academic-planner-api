from __future__ import annotations

from datetime import date

from app.schemas.availability import AvailabilityOut
from app.schemas.constraint import ConstraintOut
from app.schemas.task import TaskOut


def build_planning_context(
    tasks: list[TaskOut],
    availability_blocks: list[AvailabilityOut],
    constraints: list[ConstraintOut],
    scope: str,
    user_note: str | None = None,
    previous_plan: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "scope": scope,
        "user_note": user_note,
        "previous_plan": previous_plan,
        "tasks": [
            {
                "id": str(task.id),
                "title": task.title,
                "deadline": task.deadline.isoformat(),
                "priority": task.priority,
                "effort_estimado_min": task.effort_hours * 60,
                "status": task.status.value,
            }
            for task in tasks
        ],
        "availability_blocks": [
            {
                "id": str(block.id),
                "day": block.day.value,
                "start_time": block.start_time.isoformat(timespec="minutes"),
                "end_time": block.end_time.isoformat(timespec="minutes"),
                "label": block.label,
            }
            for block in availability_blocks
        ],
        "constraints": [
            {
                "id": str(constraint.id),
                "type": constraint.type.value,
                "description": constraint.description,
                "metadata": constraint.metadata,
            }
            for constraint in constraints
        ],
    }


def summarize_tasks(tasks: list[TaskOut]) -> dict[str, object]:
    total_effort = sum(task.effort_hours for task in tasks)
    imminent_deadline = min((task.deadline for task in tasks), default=None)
    return {
        "total_tasks": len(tasks),
        "total_effort_hours": total_effort,
        "nearest_deadline": imminent_deadline.isoformat() if imminent_deadline else None,
    }