from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .memory import SessionMemory
from .artifact_memory import recent_artifacts
from .models import AgentIntent, AssistantContext


_REPLAYABLE_TOOLS = {
    "create_visualization",
    "run_statistical_test",
    "run_regression",
    "run_automl",
    "generate_report",
}


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


    artifacts = recent_artifacts(memory)
    latest_artifact = artifacts[0] if artifacts else None
    latest_chart = next((a for a in artifacts if a.get("kind") == "chart"), None)
    latest_model = next((a for a in artifacts if a.get("kind") == "model" or a.get("model_id")), None)

    # v2.35 Context Engine v5: resolve references across several remembered
    # analytical artifacts. Selection is deterministic and refuses ambiguous
    # references instead of silently falling back to the latest item.
    if intent.name == "artifact_context":
        action = "show"
        if re.search(r"\b(?:relance|relancer|r[eé]ex[eé]cute|r[eé]ex[eé]cuter|rejoue|rejouer)\b", lowered):
            action = "replay_current" if re.search(r"\b(?:dataset|jeu de donn[eé]es)\s+actif\b|\bsur\s+(?:ce|le)\s+dataset\b", lowered) else "replay"
        elif re.search(r"\b(?:r[eé]utilise|utilise)\b.*\b(?:dataset|jeu de donn[eé]es)\s+actif\b", lowered):
            action = "replay_current"
        elif re.search(r"\bexplique|pourquoi\b", lowered):
            action = "explain"
        elif re.search(r"\bcompar", lowered):
            action = "compare"
        elif re.search(r"\b(?:refais|recr[eé]e|reprends?|r[eé]utilise)\b.*\bgraphique\b", lowered):
            action = "reuse_chart"
        elif re.search(r"\butilise\b.*\bmod[eè]le\b", lowered):
            action = "reuse_model"

        pair = _resolve_comparison_pair(text, artifacts) if action == "compare" else None
        if pair is not None:
            first, second = pair
            return ReferenceResolution(
                intent=AgentIntent(
                    name="artifact_context",
                    confidence=0.998,
                    entities={
                        **resolved_intent.entities,
                        "artifact_id": first.get("id"),
                        "artifact_ids": [first.get("id"), second.get("id")],
                        "artifact_action": "compare",
                        "reference_source": "artifact_memory_v5",
                    },
                    rationale="Deux artefacts explicitement référencés ont été résolus depuis la mémoire analytique.",
                ),
                context=resolved_context,
                inherited=True,
            )

        kind_hint = _artifact_kind_hint(lowered)
        selection = _select_artifact(text, artifacts, kind_hint=kind_hint)
        chosen = selection[0]
        candidates = selection[1]
        reason = selection[2]

        if chosen is None and candidates:
            return ReferenceResolution(
                intent=resolved_intent,
                context=resolved_context,
                clarification=_ambiguity_message(candidates, kind_hint),
            )
        if chosen is None:
            return ReferenceResolution(
                intent=resolved_intent,
                context=resolved_context,
                clarification=(
                    "Je n'ai aucun artefact analytique correspondant à cette référence dans la session active. "
                    "Lancez d'abord l'analyse, le graphique ou le modèle concerné."
                ),
            )

        # v2.38: replay a deterministic artifact through the normal governed
        # planner/executor. Stored memory is only a compact recipe: it never
        # executes directly and never bypasses Tool Registry authorization.
        if action in {"replay", "replay_current"}:
            tool = str(chosen.get("tool") or "").strip()
            params = chosen.get("params") if isinstance(chosen.get("params"), dict) else {}
            if tool not in _REPLAYABLE_TOOLS:
                return ReferenceResolution(
                    intent=resolved_intent,
                    context=resolved_context,
                    clarification=(
                        "Cet artefact peut être rappelé, mais sa recette n'est pas suffisamment compacte "
                        "pour une relance automatique sûre. Ouvrez-le puis relancez l'analyse depuis son module."
                    ),
                )
            source_dataset = str(chosen.get("dataset_id") or "") or None
            active_dataset = str(resolved_context.activeDatasetId or "") or None
            if tool != "generate_report" and not active_dataset:
                return ReferenceResolution(
                    intent=resolved_intent,
                    context=resolved_context,
                    clarification="Chargez d'abord un dataset actif avant de relancer cette analyse.",
                )
            if action == "replay" and source_dataset and active_dataset and source_dataset != active_dataset:
                return ReferenceResolution(
                    intent=resolved_intent,
                    context=resolved_context,
                    clarification=(
                        "Cette recette appartient à un autre dataset. Chargez le dataset source, "
                        "ou demandez explicitement « relance cette analyse sur le dataset actif »."
                    ),
                )
            replay_columns = _replay_columns(params)
            if replay_columns and schema:
                schema_map = {str(item.get("name")).casefold(): str(item.get("name")) for item in schema if isinstance(item, dict) and item.get("name")}
                missing = [name for name in replay_columns if name.casefold() not in schema_map]
                if missing:
                    return ReferenceResolution(
                        intent=resolved_intent,
                        context=resolved_context,
                        clarification=(
                            "Je ne peux pas relancer cette recette sur le dataset actif : "
                            "colonnes absentes — " + ", ".join(missing[:6]) + "."
                        ),
                    )
                # Preserve the current dataset's canonical casing.
                params = _remap_replay_columns(params, schema_map)
            return ReferenceResolution(
                intent=AgentIntent(
                    name="replay_artifact",
                    confidence=0.999,
                    entities={
                        "replay_tool": tool,
                        "replay_args": dict(params),
                        "artifact_id": chosen.get("id"),
                        "project_memory_id": chosen.get("project_memory_id"),
                        "source_dataset_id": source_dataset,
                        "replay_mode": "active_dataset" if action == "replay_current" else "source_dataset",
                        "reference_source": "project_memory_v8" if chosen.get("memory_source") == "project" else "artifact_memory_v8",
                    },
                    rationale="Recette analytique mémorisée résolue pour une relance gouvernée.",
                ),
                context=resolved_context,
                resolved_columns=tuple(_replay_columns(params)),
                inherited=True,
            )

        # v2.34/v2.35: contextual governed actions on the selected model. The
        # selected artifact, not merely the latest model, is authoritative.
        if re.search(r"\bmod[eè]le\b", lowered) or chosen.get("kind") == "model":
            model = chosen if chosen.get("model_id") else latest_model
            model_id = model.get("model_id") if isinstance(model, dict) else None
            if model_id:
                resolved_context.activeModelId = str(model_id)
                base_entities = {
                    **resolved_intent.entities,
                    "model_id": str(model_id),
                    "artifact_id": model.get("id"),
                    "reference_source": "artifact_memory_v5",
                    "reference_reason": reason,
                }

                target_stage = _requested_model_stage(lowered)
                if target_stage is not None:
                    return ReferenceResolution(
                        intent=AgentIntent(
                            name="model_registry",
                            confidence=0.997,
                            entities={**base_entities, "target_stage": target_stage},
                            rationale="Action de Model Registry résolue sur le modèle explicitement référencé.",
                        ),
                        context=resolved_context,
                        inherited=True,
                    )

                if re.search(r"\b(?:statut|stage|registre|registry)\b", lowered):
                    return ReferenceResolution(
                        intent=AgentIntent(
                            name="model_registry",
                            confidence=0.995,
                            entities=base_entities,
                            rationale="Lecture du statut MLOps du modèle référencé.",
                        ),
                        context=resolved_context,
                        inherited=True,
                    )

                if re.search(r"\b(?:surveille|surveiller|monitor(?:e|er|ing)?|drift|d[eé]gradation)\b", lowered):
                    return ReferenceResolution(
                        intent=AgentIntent(
                            name="monitor_model",
                            confidence=0.995,
                            entities=base_entities,
                            rationale="Monitoring demandé sur le modèle référencé.",
                        ),
                        context=resolved_context,
                        inherited=True,
                    )

                if re.search(r"\b(?:r[eé]entra[iî]n|retrain)", lowered):
                    create_request = bool(re.search(
                        r"\b(?:lance|lancer|demande|demander|cr[eé]e|cr[eé]er|programme|programmer|r[eé]entra[iî]ne)\b",
                        lowered,
                    ))
                    return ReferenceResolution(
                        intent=AgentIntent(
                            name="retraining_check",
                            confidence=0.996,
                            entities={**base_entities, "create_request": create_request},
                            rationale=(
                                "Demande de réentraînement contextualisée sur le modèle référencé."
                                if create_request
                                else "Évaluation de réentraînement contextualisée sur le modèle référencé."
                            ),
                        ),
                        context=resolved_context,
                        inherited=True,
                    )

                if re.search(r"\b(?:[eé]quit[eé]|fairness|biais)\b", lowered):
                    entities = dict(base_entities)
                    if explicit:
                        entities["protected_columns"] = list(explicit[:3])
                    return ReferenceResolution(
                        intent=AgentIntent(
                            name="fairness_analysis",
                            confidence=0.994,
                            entities=entities,
                            rationale="Audit Responsible AI contextualisé sur le modèle référencé.",
                        ),
                        context=resolved_context,
                        resolved_columns=tuple(explicit[:3]),
                        inherited=True,
                    )

                if re.search(r"\b(?:risque|responsible\s+ai|gouvernance)\b", lowered):
                    return ReferenceResolution(
                        intent=AgentIntent(
                            name="model_risk",
                            confidence=0.994,
                            entities=base_entities,
                            rationale="Évaluation de risque contextualisée sur le modèle référencé.",
                        ),
                        context=resolved_context,
                        inherited=True,
                    )

        if action == "explain" and chosen.get("model_id"):
            model_id = str(chosen.get("model_id"))
            resolved_context.activeModelId = model_id
            return ReferenceResolution(
                intent=AgentIntent(
                    name="explain_model",
                    confidence=0.995,
                    entities={
                        **resolved_intent.entities,
                        "model_id": model_id,
                        "artifact_id": chosen.get("id"),
                        "reference_source": "artifact_memory_v5",
                    },
                    rationale="Le modèle référencé est réactivé pour une explication XAI gouvernée.",
                ),
                context=resolved_context,
                inherited=True,
            )

        if action == "reuse_chart":
            chart = chosen if chosen.get("kind") == "chart" else None
            if chart is None:
                return ReferenceResolution(
                    intent=resolved_intent,
                    context=resolved_context,
                    clarification="La référence sélectionnée n'est pas un graphique réutilisable.",
                )
            params = dict(chart.get("params") or {})
            column = explicit[0] if explicit else _last_focus(memory, context)
            entities = {
                "artifact_id": chart.get("id"),
                "source_artifact_kind": "chart",
                "reference_source": "artifact_memory_v5",
            }
            if params.get("chart_type"):
                entities["chart_type"] = params.get("chart_type")
            if column:
                entities["column"] = column
                entities["x"] = column
                resolved_context.selectedEntity = _column_entity(column)
            return ReferenceResolution(
                intent=AgentIntent(
                    name="visualize",
                    confidence=0.99,
                    entities=entities,
                    rationale="Réutilisation du graphique précisément référencé par la mémoire analytique.",
                ),
                context=resolved_context,
                resolved_columns=((column,) if column else ()),
                inherited=True,
            )

        if action == "reuse_model":
            model_id = chosen.get("model_id")
            if not model_id:
                return ReferenceResolution(
                    intent=resolved_intent,
                    context=resolved_context,
                    clarification="Le résultat référencé ne contient pas de modèle réutilisable.",
                )
            resolved_context.activeModelId = str(model_id)
            entities = {
                **resolved_intent.entities,
                "model_id": str(model_id),
                "artifact_id": chosen.get("id"),
                "reference_source": "artifact_memory_v5",
            }
            if re.search(r"\bexplique|shap|importance", lowered):
                return ReferenceResolution(
                    intent=AgentIntent(
                        name="explain_model",
                        confidence=0.99,
                        entities=entities,
                        rationale="Référence au modèle sélectionné résolue depuis la mémoire analytique.",
                    ),
                    context=resolved_context,
                    inherited=True,
                )
            entities["artifact_action"] = "reuse_model"
            return ReferenceResolution(
                intent=AgentIntent(
                    name="artifact_context",
                    confidence=0.99,
                    entities=entities,
                    rationale="Le modèle sélectionné est réactivé sans inventer de valeurs de prédiction.",
                ),
                context=resolved_context,
                inherited=True,
            )

        return ReferenceResolution(
            intent=AgentIntent(
                name="artifact_context",
                confidence=0.995,
                entities={
                    **resolved_intent.entities,
                    "artifact_id": chosen.get("id"),
                    "artifact_action": action,
                    "reference_source": "artifact_memory_v5",
                    "reference_reason": reason,
                },
                rationale="Référence à un artefact analytique précisément résolue depuis la mémoire de session.",
            ),
            context=resolved_context,
            inherited=True,
        )

    # Existing model intents can inherit the most recent model artifact when the
    # UI has no active model selected.
    if intent.name in {"explain_model", "predict_target", "monitor_model", "model_risk"} and not resolved_context.activeModelId and latest_model:
        model_id = latest_model.get("model_id")
        if model_id:
            resolved_context.activeModelId = str(model_id)
            resolved_intent.entities.setdefault("model_id", str(model_id))
            resolved_intent.entities.setdefault("artifact_id", latest_model.get("id"))
            inherited = True
    # Dataset-context follow-ups such as "et sa période ?", "et ses colonnes ?"
    # inherit the active dataset explicitly instead of falling back to unknown.
    if intent.name == "unknown" and context.activeDatasetId:
        if re.fullmatch(
            r"(?:et\s+)?(?:sa|la)\s+p[eé]riode\s*[?!.]*",
            lowered,
        ) or re.fullmatch(
            r"(?:et\s+)?(?:ses|les)\s+(?:colonnes|variables)\s*[?!.]*",
            lowered,
        ) or re.fullmatch(
            r"(?:et\s+)?(?:sa|la)\s+version\s*[?!.]*",
            lowered,
        ):
            resolved_intent = AgentIntent(
                name="dataset_context",
                confidence=0.98,
                entities={
                    **memory.last_entities,
                    "dataset_id": context.activeDatasetId,
                },
                rationale="Relance factuelle résolue depuis le dataset actif.",
            )
            return ReferenceResolution(
                intent=resolved_intent,
                context=resolved_context,
                inherited=True,
            )

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

    # "Compare avec Profit" after focusing Sales -> chart Sales vs Profit.
    if intent.name == "unknown" and explicit and re.search(r"\bcompar(?:e|er)\b", lowered):
        focus = _last_focus(memory, context)
        target = explicit[0]
        if focus and focus.casefold() != target.casefold():
            resolved_intent = AgentIntent(
                name="visualize",
                confidence=0.95,
                entities={"x": focus, "y": target, "comparison": True},
                rationale="Comparaison résolue entre la variable focalisée et la variable nommée.",
            )
            return ReferenceResolution(
                intent=resolved_intent,
                context=resolved_context,
                resolved_columns=(focus, target),
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



_ARTIFACT_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "ce", "cet", "cette",
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses", "graphique",
    "modele", "modèle", "rapport", "analyse", "resultat", "résultat", "utilise", "reprends",
    "reprend", "compare", "avec", "au", "aux", "et", "contre", "precedent", "précédent",
    "avant", "dernier", "derniere", "dernière", "premier", "premiere", "première",
    "deuxieme", "deuxième", "second", "seconde", "troisieme", "troisième",
}


def _replay_columns(params: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("column", "x", "y", "target", "outcome", "group", "time_column", "comparison_column"):
        value = params.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in values:
            values.append(value.strip())
    for key in ("variables", "features", "dimensions", "protected_columns"):
        value = params.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip() and item.strip() not in values:
                    values.append(item.strip())
    return values[:16]


def _remap_replay_columns(params: dict[str, Any], schema_map: dict[str, str]) -> dict[str, Any]:
    mapped = dict(params)
    for key in ("column", "x", "y", "target", "outcome", "group", "time_column", "comparison_column"):
        value = mapped.get(key)
        if isinstance(value, str) and value.casefold() in schema_map:
            mapped[key] = schema_map[value.casefold()]
    for key in ("variables", "features", "dimensions", "protected_columns"):
        value = mapped.get(key)
        if isinstance(value, list):
            mapped[key] = [schema_map.get(str(item).casefold(), item) for item in value]
    return mapped


def _artifact_kind_hint(lowered: str) -> str | None:
    if re.search(r"\bmod[eè]les?\b", lowered):
        return "model"
    if re.search(r"\b(?:graphiques?|visualisations?|courbes?|histogrammes?)\b", lowered):
        return "chart"
    if re.search(r"\brapports?\b", lowered):
        return "report"
    if re.search(r"\b(?:analyses?|r[eé]sultats?|tests?)\b", lowered):
        return "analysis"
    return None


def _kind_candidates(artifacts: list[dict[str, Any]], kind_hint: str | None) -> list[dict[str, Any]]:
    if kind_hint is None:
        return list(artifacts)
    if kind_hint == "analysis":
        return [
            item for item in artifacts
            if item.get("kind") not in {"chart", "model", "report"}
        ]
    return [item for item in artifacts if item.get("kind") == kind_hint]


def _select_artifact(
    fragment: str,
    artifacts: list[dict[str, Any]],
    *,
    kind_hint: str | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    candidates = _kind_candidates(artifacts, kind_hint)
    if not candidates:
        return None, [], "no_candidate"
    lowered = fragment.casefold()
    normalized = _normalize(fragment)

    # Exact persisted identifiers are the strongest reference signal.
    id_matches: list[dict[str, Any]] = []
    for item in candidates:
        values = [item.get("model_id"), item.get("chart_id"), item.get("report_id"), item.get("id"), item.get("project_memory_id")]
        for value in values:
            if isinstance(value, str) and value and (value.casefold() in lowered or _normalize(value) in normalized):
                id_matches.append(item)
                break
    id_matches = _dedupe_artifacts(id_matches)
    if len(id_matches) == 1:
        return id_matches[0], id_matches, "explicit_id"
    if len(id_matches) > 1:
        return None, id_matches, "ambiguous_id"

    ordinal = _ordinal_reference(lowered)
    if ordinal is not None:
        ordered = sorted(
            candidates,
            key=lambda item: (
                int(item.get("kind_sequence") or 10**9),
                str(item.get("created_at") or ""),
            ),
        )
        if 1 <= ordinal <= len(ordered):
            return ordered[ordinal - 1], ordered, f"ordinal_{ordinal}"
        return None, ordered, "ordinal_out_of_range"

    # Demonstratives deliberately mean the most recent artifact of this kind.
    if re.search(r"\b(?:ce|cet|cette)\s+(?:graphique|mod[eè]le|rapport|analyse|r[eé]sultat|test)\b", lowered):
        return candidates[0], candidates, "deictic_latest"

    scored: list[tuple[int, dict[str, Any]]] = []
    for item in candidates:
        score = _artifact_match_score(fragment, item)
        if score > 0:
            scored.append((score, item))
    if scored:
        scored.sort(key=lambda pair: pair[0], reverse=True)
        best_score = scored[0][0]
        best = [item for score, item in scored if score == best_score]
        if len(best) == 1:
            return best[0], best, "named_match"
        return None, best, "ambiguous_named_match"

    if re.search(r"\b(?:dernier|derni[eè]re|plus\s+r[eé]cent)\b", lowered):
        return candidates[0], candidates, "latest"
    if re.search(r"\b(?:pr[eé]c[eé]dent|d['’]avant|avant)\b", lowered):
        if len(candidates) >= 2:
            return candidates[1], candidates, "previous"
        return candidates[0], candidates, "only_candidate"

    if len(candidates) == 1:
        return candidates[0], candidates, "only_candidate"
    return None, candidates, "ambiguous_generic"


def _resolve_comparison_pair(
    message: str,
    artifacts: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    lowered = message.casefold()
    if not re.search(r"\bcompar(?:e|er|aison)\b", lowered):
        return None
    kind_hint = _artifact_kind_hint(lowered)
    candidates = _kind_candidates(artifacts, kind_hint)
    if len(candidates) < 2:
        return None

    # "compare les deux modèles" is deterministic only when exactly two exist.
    if re.search(r"\b(?:les\s+)?deux\s+(?:mod[eè]les?|graphiques?|rapports?|analyses?|r[eé]sultats?)\b", lowered):
        if len(candidates) == 2:
            return candidates[0], candidates[1]
        return None

    match = re.search(
        r"\bcompar(?:e|er|aison)?\b\s+(.+?)\s+(?:au|à|avec|contre|vs\.?|et)\s+(.+?)\s*[?!.]*$",
        message,
        re.IGNORECASE,
    )
    if not match:
        return None
    left_text, right_text = match.group(1), match.group(2)
    left, _, _ = _select_artifact(left_text, artifacts, kind_hint=kind_hint)
    right, _, _ = _select_artifact(right_text, artifacts, kind_hint=kind_hint)
    if left is not None and right is not None and left.get("id") != right.get("id"):
        return left, right
    return None


def _artifact_match_score(fragment: str, item: dict[str, Any]) -> int:
    lowered = fragment.casefold()
    normalized = _normalize(fragment)
    score = 0

    aliases = item.get("aliases") if isinstance(item.get("aliases"), list) else []
    values = [
        item.get("reference_name"), item.get("display_name"), item.get("label"),
        item.get("model_id"), item.get("chart_id"), item.get("report_id"),
        *aliases,
    ]
    params = item.get("params") if isinstance(item.get("params"), dict) else {}
    values.extend(params.get(key) for key in ("algorithm", "target", "chart_type", "name", "title"))
    values.extend(item.get("columns") or [])

    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        token = value.strip()
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        norm = _normalize(token)
        if len(norm) < 2:
            continue
        if key in lowered:
            score += 8 if len(norm) >= 5 else 5
        elif norm and norm in normalized:
            score += 5

    # Token overlap handles friendly names such as "prévision ventes" without
    # relying on a language model. Generic artifact words never earn points.
    query_tokens = {
        _normalize(token)
        for token in re.findall(r"[\wÀ-ÿ.-]+", fragment, flags=re.UNICODE)
        if token.casefold() not in _ARTIFACT_STOPWORDS and len(_normalize(token)) >= 3
    }
    searchable = " ".join(str(value) for value in values if isinstance(value, str))
    search_tokens = {
        _normalize(token)
        for token in re.findall(r"[\wÀ-ÿ.-]+", searchable, flags=re.UNICODE)
        if len(_normalize(token)) >= 3
    }
    score += 2 * len(query_tokens & search_tokens)
    return score


def _ordinal_reference(lowered: str) -> int | None:
    ordinal_patterns = (
        (1, r"\b(?:premier|premi[eè]re|1er|1[eè]re|#?1)\b"),
        (2, r"\b(?:deuxi[eè]me|second|seconde|2e|2[eè]me|#?2)\b"),
        (3, r"\b(?:troisi[eè]me|3e|3[eè]me|#?3)\b"),
        (4, r"\b(?:quatri[eè]me|4e|4[eè]me|#?4)\b"),
        (5, r"\b(?:cinqui[eè]me|5e|5[eè]me|#?5)\b"),
    )
    for value, pattern in ordinal_patterns:
        if re.search(pattern, lowered):
            return value
    return None


def _dedupe_artifacts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = str(item.get("id") or "")
        if key and key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _ambiguity_message(candidates: list[dict[str, Any]], kind_hint: str | None) -> str:
    if not candidates:
        return "Je n'ai pas pu résoudre cette référence analytique."
    noun = {
        "model": "modèles",
        "chart": "graphiques",
        "report": "rapports",
        "analysis": "analyses/résultats",
    }.get(kind_hint, "résultats")
    options: list[str] = []
    for index, item in enumerate(candidates[:5], start=1):
        ref = str(item.get("reference_name") or item.get("label") or f"Résultat {index}")
        detail = str(item.get("label") or item.get("summary") or "")
        identifier = item.get("model_id") or item.get("chart_id") or item.get("report_id")
        text = f"{index}) {ref}"
        if detail and detail != ref:
            text += f" — {detail}"
        if identifier:
            text += f" [{identifier}]"
        options.append(text)
    return (
        f"J'ai trouvé plusieurs {noun} possibles et je ne veux pas choisir à votre place : "
        + " ; ".join(options)
        + ". Dites par exemple « le premier », « le deuxième » ou donnez son identifiant."
    )


def _requested_model_stage(lowered: str) -> str | None:
    """Return a stage only when the user explicitly asks for a transition.

    Merely mentioning that a model is already "en production" must never be
    interpreted as a request to mutate its registry stage.
    """
    transition = re.search(
        r"\b(?:met|mets|mettre|passe|passer|promouvois|promouvoir|d[eé]ploie|d[eé]ployer|"
        r"place|placer|bascule|basculer|publie|publier|retire|retirer|archive|archiver)\b",
        lowered,
    )
    if not transition:
        return None
    if re.search(r"\b(?:publie|publier)\b", lowered):
        return "production"
    if re.search(r"\b(?:production|prod)\b", lowered):
        return "production"
    if re.search(r"\b(?:staging|pr[eé][ -]?production)\b", lowered):
        return "staging"
    if re.search(r"\b(?:draft|brouillon)\b", lowered):
        return "draft"
    if re.search(r"\b(?:retired|retire|retir[eé]|archive|archiv[eé])\b", lowered):
        return "retired"
    return None

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
