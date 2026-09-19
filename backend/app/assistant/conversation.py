from __future__ import annotations

from dataclasses import dataclass
import re

from .models import AgentIntent, AgentTurnResponse, AssistantContext
from .memory import SessionMemoryStore
from .result_composer import compose_run_results
from .artifact_memory import recent_artifacts
from .project_memory import list_entries as list_project_memory, search_entries as search_project_memory, scope_for_context as project_memory_scope_for_context
from .turn_runs import AgentTurnRunStore


@dataclass
class ConversationalResponder:
    turn_store: AgentTurnRunStore
    memory: SessionMemoryStore | None = None

    def respond(
        self,
        *,
        session_id: str,
        message: str,
        intent: AgentIntent,
        context: AssistantContext,
    ) -> AgentTurnResponse | None:
        if intent.name == "show_results":
            latest = self.turn_store.latest_for_session(
                session_id,
                statuses={"completed", "partial"},
            )
            if latest is None:
                answer = (
                    "Je n'ai pas encore de résultat d'analyse dans cette session. "
                    "Demandez-moi par exemple d'analyser le dataset actif."
                )
            else:
                answer = compose_run_results(latest)
            return self._response(session_id, intent, answer)


        if intent.name == "project_memory":
            try:
                scope_id, _workspace_id, _user_id = project_memory_scope_for_context(context)
                entries = search_project_memory(
                    scope_id,
                    message,
                    dataset_id=context.activeDatasetId,
                    limit=8,
                )
                if not entries:
                    entries = list_project_memory(scope_id, limit=8)
                if not entries:
                    answer = (
                        "La mémoire projet ne contient encore aucun artefact analytique réutilisable. "
                        "Elle se remplit uniquement avec des résultats déterministes créés par DataVision, "
                        "pas avec le transcript brut de vos conversations."
                    )
                else:
                    lines = []
                    for index, entry in enumerate(entries[:8], 1):
                        title = str(entry.get("title") or entry.get("kind") or f"Résultat {index}")
                        summary = str(entry.get("summary") or "")
                        pinned = " · épinglé" if entry.get("pinned") else ""
                        score = entry.get("search_score")
                        score_note = f" · pertinence {float(score) * 100:.0f} %" if isinstance(score, (int, float)) else ""
                        lines.append(f"{index}) {title}{pinned}{score_note} — {summary}")
                    answer = (
                        "Voici les éléments que je peux rappeler dans ce projet :\n"
                        + "\n".join(lines)
                        + "\nVous pouvez citer un identifiant, un nom, ou dire par exemple « reprends l'analyse d'avant »."
                    )
                response = self._response(session_id, intent, answer)
                response.metadata.update({
                    "project_memory_recall": [
                        {
                            "id": entry.get("id"),
                            "artifact_id": entry.get("artifact_id"),
                            "kind": entry.get("kind"),
                            "title": entry.get("title"),
                            "summary": entry.get("summary"),
                            "dataset_id": entry.get("dataset_id"),
                            "pinned": entry.get("pinned"),
                            "created_at": entry.get("created_at"),
                            "search_score": entry.get("search_score"),
                            "match_reasons": entry.get("match_reasons"),
                        }
                        for entry in entries[:8]
                    ],
                    "project_memory_scope": scope_id,
                })
                return response
            except Exception:
                return self._response(
                    session_id, intent,
                    "La mémoire projet est momentanément indisponible. La mémoire de cette session reste utilisable."
                )

        if intent.name == "artifact_context":
            item = self.memory.get_or_create(session_id) if self.memory is not None else None
            artifacts = recent_artifacts(item) if item is not None else []
            by_id = {str(a.get("id")): a for a in artifacts}
            action = str(intent.entities.get("artifact_action") or "show")
            artifact_id = str(intent.entities.get("artifact_id") or "")
            artifact = by_id.get(artifact_id) or (artifacts[0] if artifacts else None)
            if artifact is None:
                return self._response(session_id, intent, "Je n'ai pas encore de résultat analytique récent à référencer.")

            if action == "compare":
                ids = intent.entities.get("artifact_ids") if isinstance(intent.entities.get("artifact_ids"), list) else []
                pair = [by_id.get(str(value)) for value in ids[:2]]
                pair = [value for value in pair if value is not None]
                if len(pair) < 2:
                    return self._response(session_id, intent, "Je n'ai pas deux résultats récents suffisamment identifiés pour faire cette comparaison.")
                first, second = pair[0], pair[1]
                common = sorted(set((first.get("metrics") or {}).keys()) & set((second.get("metrics") or {}).keys()))
                details = []
                for key in common[:4]:
                    a = (first.get("metrics") or {}).get(key)
                    b = (second.get("metrics") or {}).get(key)
                    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                        delta = float(a) - float(b)
                        details.append(f"{key}: {a:.5g} vs {b:.5g} (écart {delta:+.5g})")
                answer = f"Résultat récent : {first.get('summary')}. Résultat précédent : {second.get('summary')}."
                if details:
                    answer += " Comparaison déterministe : " + "; ".join(details) + "."
                else:
                    answer += " Les deux artefacts n'exposent pas de métrique numérique commune ; je ne vais pas fabriquer une comparaison quantitative."
                return self._response(session_id, intent, answer)

            if action == "reuse_model":
                model_id = artifact.get("model_id")
                answer = (
                    f"Le modèle précédent est maintenant référencé dans le contexte (ID {model_id}). "
                    "Pour produire une prédiction, donnez les valeurs de l'observation à scorer "
                    "ou utilisez un déploiement de modèle déjà configuré. Je ne vais pas inventer les features d'entrée."
                )
                return self._response(session_id, intent, answer)

            if action == "explain":
                answer = (
                    f"Le résultat référencé est : {artifact.get('summary')}. "
                    f"Il provient de l'outil déterministe « {artifact.get('tool')} ». "
                    "Je peux expliquer les métriques déjà calculées, mais une conclusion causale supplémentaire nécessite une analyse dédiée."
                )
                return self._response(session_id, intent, answer)

            return self._response(session_id, intent, f"Résultat référencé : {artifact.get('summary')}.")
        if intent.name == "dataset_context":
            facts = context.uiState or {}
            lower = message.casefold()
            dataset_name = str(facts.get("datasetName") or "le dataset actif")
            version = facts.get("datasetVersion") or context.activeDatasetVersionId
            rows = _to_int(facts.get("rowCount"))
            columns = _to_int(facts.get("columnCount"))
            schema = facts.get("datasetSchema") if isinstance(facts.get("datasetSchema"), list) else []
            temporal = facts.get("temporalCoverage") if isinstance(facts.get("temporalCoverage"), dict) else {}
            primary = temporal.get("primary") if isinstance(temporal.get("primary"), dict) else None

            period_question = any(token in lower for token in (
                "période", "periode", "remonte", "depuis quand",
                "jusqu'à quand", "jusqu’à quand", "date la plus",
                "couverture temporelle", "plage de date", "plage de dates",
            ))
            if period_question:
                if primary and primary.get("start") and primary.get("end"):
                    start = _display_date(primary.get("start"), primary.get("kind"))
                    end = _display_date(primary.get("end"), primary.get("kind"))
                    column = primary.get("column") or "la variable temporelle détectée"
                    confidence = _to_float(primary.get("confidence"))
                    confidence_note = (
                        f" (confiance {confidence * 100:.0f} %)"
                        if confidence is not None else ""
                    )
                    answer = (
                        f"Le dataset actif « {dataset_name} » couvre la période du {start} au {end}, "
                        f"d'après la colonne « {column} »{confidence_note}."
                    )
                    temporal_columns = temporal.get("columns") if isinstance(temporal.get("columns"), list) else []
                    if len(temporal_columns) > 1:
                        others = [str(item.get("column")) for item in temporal_columns[1:4] if isinstance(item, dict) and item.get("column")]
                        if others:
                            answer += " Autres colonnes temporelles détectées : " + ", ".join(others) + "."
                else:
                    answer = (
                        f"Je connais bien le dataset actif « {dataset_name} », mais le profil actuel "
                        "ne contient aucune colonne temporelle suffisamment fiable pour déterminer sa période. "
                        "Je ne vais pas inventer une date."
                    )
                return self._response(session_id, intent, answer)

            if "combien" in lower and "ligne" in lower:
                answer = f"Le dataset actif « {dataset_name} » contient {rows} lignes." if rows is not None else "Le nombre de lignes n'est pas disponible dans le contexte courant."
                return self._response(session_id, intent, answer)

            if "combien" in lower and ("colonne" in lower or "variable" in lower):
                answer = f"Le dataset actif « {dataset_name} » contient {columns} variables." if columns is not None else "Le nombre de variables n'est pas disponible dans le contexte courant."
                return self._response(session_id, intent, answer)

            if (
                (("quelles" in lower or "quels" in lower) and ("colonne" in lower or "variable" in lower))
                or re.search(r"\b(?:ses|les)\s+(?:colonnes|variables)\b", lower)
            ):
                names = [str(item.get("name")) for item in schema if isinstance(item, dict) and item.get("name")]
                if names:
                    shown = names[:30]
                    suffix = f" … (+{len(names)-30})" if len(names) > 30 else ""
                    answer = "Colonnes du dataset actif : " + ", ".join(shown) + suffix + "."
                else:
                    answer = "Le schéma du dataset n'est pas disponible dans le contexte courant."
                return self._response(session_id, intent, answer)

            if "version" in lower:
                answer = f"Le dataset actif « {dataset_name} » est en version {version}." if version is not None else f"Le dataset actif est « {dataset_name} », mais sa version n'est pas disponible."
                return self._response(session_id, intent, answer)

            if "dataset actif" in lower or "nom" in lower:
                details = [f"Le dataset actif est « {dataset_name} »"]
                if version is not None:
                    details.append(f"version {version}")
                if rows is not None and columns is not None:
                    details.append(f"{rows} lignes × {columns} variables")
                return self._response(session_id, intent, ", ".join(details) + ".")

            # Generic context summary for dataset-specific factual questions.
            details = [f"Dataset actif : « {dataset_name} »"]
            if version is not None:
                details.append(f"v{version}")
            if rows is not None:
                details.append(f"{rows} lignes")
            if columns is not None:
                details.append(f"{columns} variables")
            if primary and primary.get("start") and primary.get("end"):
                details.append(
                    f"période {_display_date(primary.get('start'), primary.get('kind'))} → "
                    f"{_display_date(primary.get('end'), primary.get('kind'))}"
                )
            return self._response(session_id, intent, " · ".join(details) + ".")

        if intent.name == "dataset_assessment":
            facts = context.uiState or {}
            dataset_name = facts.get("datasetName") or "le dataset actif"
            rows = _to_int(facts.get("rowCount"))
            columns = _to_int(facts.get("columnCount"))
            missing = _to_int(facts.get("missingCells"))
            duplicates = _to_int(facts.get("duplicateCount"))
            quality = _to_float(facts.get("qualityScore"))
            issue_count = _to_int(facts.get("qualityIssuesCount"))
            numeric_count = _to_int(facts.get("numericColumnCount"))
            categorical_count = _to_int(facts.get("categoricalColumnCount"))

            if (
                rows is None
                and columns is None
                and quality is None
                and missing is None
                and duplicates is None
            ):
                answer = (
                    "Je vois qu'un dataset est actif, mais je n'ai pas encore assez "
                    "d'indicateurs de profilage pour donner un avis fondé. "
                    "Je peux le profiler et vérifier sa qualité si vous le souhaitez."
                )
                return self._response(session_id, intent, answer)

            parts: list[str] = []

            if quality is not None:
                if quality >= 90:
                    verdict = "très bonne"
                elif quality >= 80:
                    verdict = "bonne"
                elif quality >= 60:
                    verdict = "correcte mais perfectible"
                else:
                    verdict = "fragile et à corriger avant une analyse avancée"

                parts.append(
                    f"La qualité globale de {dataset_name} est {verdict} "
                    f"avec un score de {quality:g}/100."
                )
            else:
                parts.append(
                    f"Voici mon appréciation factuelle de {dataset_name}."
                )

            structure: list[str] = []
            if rows is not None:
                structure.append(f"{rows} lignes")
            if columns is not None:
                structure.append(f"{columns} variables")
            if structure:
                parts.append("Il contient " + " et ".join(structure) + ".")

            hygiene: list[str] = []
            if missing is not None:
                hygiene.append(
                    "aucune cellule manquante"
                    if missing == 0
                    else (
                        f"{missing} cellule{'s' if missing > 1 else ''} "
                        f"manquante{'s' if missing > 1 else ''}"
                    )
                )
            if duplicates is not None:
                hygiene.append(
                    "aucun doublon"
                    if duplicates == 0
                    else f"{duplicates} doublon{'s' if duplicates > 1 else ''}"
                )
            if hygiene:
                parts.append(
                    "Sur l'hygiène des données : "
                    + " et ".join(hygiene)
                    + "."
                )

            typing: list[str] = []
            if numeric_count is not None:
                typing.append(
                    f"{numeric_count} variable"
                    f"{'s' if numeric_count != 1 else ''} numérique"
                    f"{'s' if numeric_count != 1 else ''}"
                )
            if categorical_count is not None:
                typing.append(
                    f"{categorical_count} variable"
                    f"{'s' if categorical_count != 1 else ''} catégorielle"
                    f"{'s' if categorical_count != 1 else ''}"
                )
            if typing:
                parts.append("Structure : " + " et ".join(typing) + ".")

            if issue_count is not None and issue_count > 0:
                parts.append(
                    f"DataVision signale toutefois {issue_count} problème"
                    f"{'s' if issue_count > 1 else ''} de qualité à examiner."
                )
            elif (
                quality is not None
                and quality >= 80
                and missing == 0
                and duplicates == 0
            ):
                parts.append(
                    "C'est une base saine pour poursuivre l'exploration, "
                    "mais je vérifierais encore les distributions, les valeurs aberrantes "
                    "et la pertinence métier des variables avant de modéliser."
                )
            else:
                parts.append(
                    "Avant de modéliser, je recommande de vérifier les distributions, "
                    "les valeurs aberrantes et les variables potentiellement identifiantes."
                )

            answer = " ".join(parts)
            return self._response(session_id, intent, answer)


        if intent.name == "explain_previous":
            item = (
                self.memory.get_or_create(session_id)
                if self.memory is not None
                else None
            )
            latest = self.turn_store.latest_for_session(
                session_id,
                statuses={"completed", "partial"},
            )

            if item and item.last_result_summary:
                previous = item.last_result_summary
            elif latest is not None:
                previous = compose_run_results(latest)
            else:
                previous = None

            if not previous:
                answer = (
                    "Je n'ai pas assez de contexte précédent pour expliquer « pourquoi ». "
                    "Précisez le résultat ou l'observation que vous voulez comprendre."
                )
            else:
                answer = (
                    "Parce que mon appréciation repose uniquement sur les faits déjà calculés "
                    "par DataVision. Le point de départ était : "
                    f"{previous} "
                    "Si vous voulez une explication causale ou statistique plus profonde, "
                    "je peux lancer l'analyse appropriée au lieu de l'inventer."
                )

            return self._response(session_id, intent, answer)

        if intent.name == "capabilities":
            answer = (
                "Dans DataVision, je peux analyser les datasets chargés, lancer les moteurs "
                "statistiques et ML autorisés, créer des visualisations, préparer des rapports "
                "et agir via les connecteurs configurés. "
                "Je n'ai pas de navigation Internet générale dans cette version. "
                "Un accès externe n'est possible que via un provider ou un connecteur explicitement "
                "configuré et autorisé par les règles de confidentialité DataVision."
            )
            return self._response(session_id, intent, answer)

        if intent.name == "conversation":
            lower = message.lower().strip()
            if lower.startswith(("bonjour", "bonsoir", "salut", "hello", "hey")):
                answer = (
                    "Bonjour. Je suis DataVision AI. "
                    "Posez-moi une question sur le dataset actif ou demandez-moi une analyse précise."
                )
            elif "merci" in lower:
                answer = "Avec plaisir."
            elif "qui es" in lower:
                answer = (
                    "Je suis l'assistant DataVision AI. "
                    "Je travaille avec le contexte de l'application et les moteurs gouvernés de DataVision."
                )
            else:
                answer = "Je vous écoute."
            return self._response(session_id, intent, answer)

        return None

    @staticmethod
    def _response(
        session_id: str,
        intent: AgentIntent,
        answer: str,
    ) -> AgentTurnResponse:
        return AgentTurnResponse(
            session_id=session_id,
            intent=intent,
            message=answer,
            speak=True,
            status="completed",
            steps=[],
            metadata={"conversation_only": True},
        )


def _display_date(value, kind=None):
    if value is None:
        return "—"
    text = str(value)
    if kind == "year" and len(text) >= 4:
        return text[:4]
    # ISO dates are displayed compactly while retaining exact day information.
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    return text


def _to_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
