from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .memory import SessionMemory
from .models import AgentIntent, AssistantContext


FOLLOWUP_PREFIXES = (
    "et ",
    "alors ",
    "donc ",
    "maintenant ",
    "pareil ",
    "même chose ",
    "fais pareil",
    "fais la même chose",
    "montre-moi ça",
    "montre moi ça",
)


@dataclass(frozen=True)
class ReferenceResolution:
    intent: AgentIntent
    context: AssistantContext
    clarification: str | None = None
    resolved_columns: tuple[str, ...] = ()
    inherited: bool = False


def resolve_references(
    *,
    message: str,
    intent: AgentIntent,
    context: AssistantContext,
    memory: SessionMemory,
) -> ReferenceResolution:
    text = message.strip()
    lowered = text.casefold()
    schema = _schema_columns(context)

    # Track explicit column mentions even when the deterministic intent resolver
    # already understood the operation.
    explicit = _mentioned_columns(text, schema)

    resolved_context = context.model_copy(deep=True)
    resolved_intent = intent.model_copy(deep=True)
    inherited = False

    # "Et pourquoi ?" / "Pourquoi ?" after a result or assessment.
    if (
        intent.name == "unknown"
        and re.fullmatch(
            r"(?:et\s+)?pourquoi\s*[?!.]*",
            lowered,
        )
    ):
        resolved_intent = AgentIntent(
            name="explain_previous",
            confidence=0.99,
            entities=dict(memory.last_entities),
            rationale="Relance explicative liée au tour précédent.",
        )
        return ReferenceResolution(
            intent=resolved_intent,
            context=resolved_context,
            inherited=True,
        )

    # "Fais pareil avec Profit", "même chose pour Sales", ...
    same_as_match = re.search(
        r"(?:pareil|m[eê]me\s+chose|la\s+m[eê]me\s+chose)"
        r".*?(?:avec|pour)\s+(.+?)\s*[?!.]*$",
        lowered,
    )
    if same_as_match and memory.last_intent:
        candidate_text = same_as_match.group(1)
        column = _best_column(candidate_text, schema)
        if column:
            inherited_intent = _inheritable_intent(memory.last_intent)
            if inherited_intent:
                resolved_intent = AgentIntent(
                    name=inherited_intent,
                    confidence=0.96,
                    entities={
                        **memory.last_entities,
                        "column": column,
                        "x": column,
                    },
                    rationale=(
                        "Réutilisation de la dernière opération avec une nouvelle variable."
                    ),
                )
                resolved_context.selectedEntity = _column_entity(column)
                return ReferenceResolution(
                    intent=resolved_intent,
                    context=resolved_context,
                    resolved_columns=(column,),
                    inherited=True,
                )

    # "Montre-moi ça en graphique" should inherit the most recent focused column.
    if intent.name == "visualize" and not explicit:
        focus = _last_focus(memory, context)
        if focus:
            resolved_intent.entities["column"] = focus
            resolved_intent.entities["x"] = focus
            resolved_context.selectedEntity = _column_entity(focus)
            inherited = True

    # If a natural request mentions a real schema column, attach it to the
    # semantic entity set for deterministic planners.
    if explicit:
        primary = explicit[0]
        resolved_intent.entities.setdefault("column", primary)
        resolved_intent.entities.setdefault("x", primary)
        if (
            resolved_context.selectedEntity is None
            or resolved_context.selectedEntity.type not in {"column", "variable"}
        ):
            resolved_context.selectedEntity = _column_entity(primary)

    # "Compare-le avec l'autre" is safe only when two recent columns are known.
    if (
        intent.name == "unknown"
        and re.search(
            r"\bcompar(?:e|er)\b.*\b(?:le|la|ça|ca)\b.*\bl['’]?autre\b",
            lowered,
        )
    ):
        columns = _unique_existing(memory.recent_columns, schema)
        if len(columns) >= 2:
            x, y = columns[0], columns[1]
            resolved_intent = AgentIntent(
                name="visualize",
                confidence=0.94,
                entities={
                    "x": x,
                    "y": y,
                    "comparison": True,
                },
                rationale=(
                    "Comparaison résolue depuis les deux variables récemment focalisées."
                ),
            )
            return ReferenceResolution(
                intent=resolved_intent,
                context=resolved_context,
                resolved_columns=(x, y),
                inherited=True,
            )
        return ReferenceResolution(
            intent=resolved_intent,
            context=resolved_context,
            clarification=(
                "Je comprends que vous voulez comparer deux variables, mais « l'autre » "
                "n'est pas suffisamment déterminé. Sélectionnez ou nommez la deuxième variable."
            ),
        )

    # Elliptical follow-up with no reliable intent. We only inherit operations
    # when the wording explicitly signals continuation.
    if (
        intent.name == "unknown"
        and memory.last_intent
        and any(lowered.startswith(prefix) for prefix in FOLLOWUP_PREFIXES)
    ):
        inheritable = _inheritable_intent(memory.last_intent)
        focus = explicit[0] if explicit else _last_focus(memory, context)
        if inheritable and focus:
            resolved_intent = AgentIntent(
                name=inheritable,
                confidence=0.82,
                entities={
                    **memory.last_entities,
                    "column": focus,
                    "x": focus,
                },
                rationale="Relance elliptique résolue depuis la mémoire de session.",
            )
            resolved_context.selectedEntity = _column_entity(focus)
            inherited = True

    resolved_columns = tuple(explicit)
    return ReferenceResolution(
        intent=resolved_intent,
        context=resolved_context,
        resolved_columns=resolved_columns,
        inherited=inherited,
    )


def _schema_columns(context: AssistantContext) -> list[dict[str, Any]]:
    schema = context.uiState.get("datasetSchema") if context.uiState else None
    if not isinstance(schema, list):
        return []
    result = []
    for item in schema:
        if isinstance(item, dict) and item.get("name"):
            result.append(
                {
                    "name": str(item["name"]),
                    "dtype": str(item.get("dtype") or ""),
                }
            )
    return result


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _mentioned_columns(
    message: str,
    schema: list[dict[str, Any]],
) -> list[str]:
    lowered = message.casefold()
    normalized_message = _normalize(message)
    matches: list[tuple[int, str]] = []
    for item in schema:
        name = item["name"]
        if name.casefold() in lowered or _normalize(name) in normalized_message:
            matches.append((len(name), name))
    matches.sort(reverse=True)
    return [name for _length, name in matches]


def _best_column(
    fragment: str,
    schema: list[dict[str, Any]],
) -> str | None:
    normalized = _normalize(fragment)
    if not normalized:
        return None
    exact = [
        item["name"]
        for item in schema
        if _normalize(item["name"]) == normalized
    ]
    if exact:
        return exact[0]
    contained = [
        item["name"]
        for item in schema
        if _normalize(item["name"]) in normalized
        or normalized in _normalize(item["name"])
    ]
    if len(contained) == 1:
        return contained[0]
    return None


def _last_focus(
    memory: SessionMemory,
    context: AssistantContext,
) -> str | None:
    if memory.recent_columns:
        return memory.recent_columns[0]
    selected = context.selectedEntity
    if (
        selected
        and selected.type in {"column", "variable"}
        and selected.id
    ):
        return selected.id
    return None


def _inheritable_intent(intent: str) -> str | None:
    if intent in {
        "visualize",
        "data_quality",
        "dataset_assessment",
        "analyze_dataset",
    }:
        return intent
    return None


def _unique_existing(
    columns: list[str],
    schema: list[dict[str, Any]],
) -> list[str]:
    known = {item["name"].casefold(): item["name"] for item in schema}
    result: list[str] = []
    for column in columns:
        canonical = known.get(column.casefold())
        if canonical and canonical not in result:
            result.append(canonical)
    return result


def _column_entity(column: str):
    from .models import SelectedEntity

    return SelectedEntity(
        type="column",
        id=column,
        label=column,
    )
