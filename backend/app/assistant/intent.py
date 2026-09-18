from __future__ import annotations

import re
from dataclasses import dataclass

from .models import AgentIntent, AssistantContext


@dataclass(frozen=True)
class IntentRule:
    name: str
    patterns: tuple[str, ...]
    confidence: float


RULES: tuple[IntentRule, ...] = (
    IntentRule(
        "predict_target",
        (
            r"\bpr[eé]di(?:re|ction|s)\b",
            r"\bclassification\b",
            r"\br[eé]gression\b",
            r"\bautoml\b",
            r"\bforecast",
        ),
        0.92,
    ),
    IntentRule(
        "compare_groups",
        (
            r"\bcompar(?:e|er|aison)\b.*\bgroup",
            r"\bdeux groupes\b",
            r"\btest statistique\b",
            r"\banova\b",
            r"\bt[- ]?test\b",
        ),
        0.90,
    ),
    IntentRule(
        "geospatial_analysis",
        (
            r"\bsig\b",
            r"\bgis\b",
            r"\bspatial",
            r"\breproje",
            r"\bbuffer\b",
            r"\bcouche\b.*\bcarte\b",
        ),
        0.92,
    ),
    IntentRule(
        "visualize",
        (
            r"\bgraph(?:ique|iques)\b",
            r"\bvisualis",
            r"\bhistogram",
            r"\bscatter\b",
            r"\bheatmap\b",
            r"\bcourbe\b",
        ),
        0.88,
    ),
    IntentRule(
        "data_quality",
        (
            r"\bnetto",
            r"\bmanqu",
            r"\bdoublon",
            r"\bqualit[eé]\b",
            r"\boutlier",
            r"\bvaleur aberrante",
        ),
        0.88,
    ),
    IntentRule(
        "explain_model",
        (
            r"\bexplique\b.*\bmod[eè]le\b",
            r"\bshap\b",
            r"\bimportance des variables\b",
            r"\bfeature importance\b",
        ),
        0.91,
    ),
    IntentRule(
        "report",
        (
            r"\brapport\b",
            r"\bpdf\b",
            r"\bdocx\b",
            r"\bpptx\b",
            r"\bpowerpoint\b",
        ),
        0.85,
    ),
    IntentRule(
        "file_analysis",
        (
            r"\bce fichier\b",
            r"\bfichier excel\b",
            r"\bcsv\b",
            r"\bpdf\b.*\banalyse",
        ),
        0.80,
    ),
    IntentRule(
        "analyze_dataset",
        (
            r"\banalyse\b",
            r"\banalyser\b",
            r"\bexplore\b",
            r"\bcomprends?\b.*\bdonn",
        ),
        0.78,
    ),
)


def resolve_intent(message: str, context: AssistantContext) -> AgentIntent:
    text = message.lower().strip()
    best: AgentIntent | None = None

    for rule in RULES:
        for pattern in rule.patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                entities = _extract_entities(text, context)
                candidate = AgentIntent(
                    name=rule.name,
                    confidence=rule.confidence,
                    entities=entities,
                    rationale=f"Correspondance déterministe avec le motif: {pattern}",
                )
                if best is None or candidate.confidence > best.confidence:
                    best = candidate
                break

    if best is not None:
        return best

    if context.activeDatasetId:
        return AgentIntent(
            name="analyze_dataset",
            confidence=0.55,
            entities=_extract_entities(text, context),
            rationale="Fallback sur le dataset actif.",
        )

    return AgentIntent(
        name="unknown",
        confidence=0.25,
        entities={},
        rationale="Aucune intention fiable détectée.",
    )


def _extract_entities(text: str, context: AssistantContext) -> dict:
    entities: dict = {}

    if context.activeDatasetId:
        entities["dataset_id"] = context.activeDatasetId
    if context.activeModelId:
        entities["model_id"] = context.activeModelId

    target_patterns = (
        r"\bcible\s+([a-zA-Z0-9_]+)",
        r"\btarget\s+([a-zA-Z0-9_]+)",
        r"\bpr[eé]dire\s+(?:la|le|les|l['’])?\s*([a-zA-Z0-9_]+)",
    )
    reserved = {"cible", "target", "variable", "colonne", "valeur"}

    for pattern in target_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1)
            if candidate.lower() not in reserved:
                entities["target"] = candidate
                break

    if re.search(r"\bclassification\b", text):
        entities["ml_task"] = "classification"
    elif re.search(r"\br[eé]gression\b", text):
        entities["ml_task"] = "regression"
    elif re.search(r"\bforecast(?:ing)?\b|\bpr[eé]vision temporelle\b", text):
        entities["ml_task"] = "forecasting"
    elif re.search(r"\bclustering\b|\bsegmentation non supervis", text):
        entities["ml_task"] = "clustering"

    # Conservative extraction: do not guess statistical columns from arbitrary nouns.
    return entities
