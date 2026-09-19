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
        "show_results",
        (
            r"\bo[uù]\s+sont\s+(?:les\s+)?r[eé]sultats?\b",
            r"\bmontre(?:-moi)?\s+(?:les\s+)?r[eé]sultats?\b",
            r"\bquels?\s+(?:sont\s+)?(?:les\s+)?r[eé]sultats?\b",
            r"\bqu['’]as[- ]tu\s+trouv[eé]\b",
            r"\bqu['’]est[- ]ce\s+que\s+tu\s+as\s+trouv[eé]\b",
            r"\br[eé]sum[eé]\s+(?:les\s+)?r[eé]sultats?\b",
            r"\br[eé]sultat\s+de\s+l['’]analyse\b",
        ),
        0.98,
    ),

IntentRule(
    "dataset_assessment",
    (
        r"\bcomment\s+(?:tu\s+)?trouv(?:e|es)[- ]?(?:tu)?\s+(?:le|ce|mon)?\s*dataset\b",
        r"\bcomment\s+(?:tu\s+)?trouv(?:e|es)[- ]?(?:tu)?\s+(?:les|mes|ces)?\s*donn[eé]es\b",
        r"\bqu['’]est[- ]ce\s+que\s+tu\s+penses?\s+(?:du|de\s+ce|des)\s+(?:dataset|donn[eé]es)\b",
        r"\bque\s+penses[- ]tu\s+(?:du|de\s+ce|des)\s+(?:dataset|donn[eé]es)\b",
        r"\bton\s+avis\s+sur\s+(?:le|ce|mon)?\s*(?:dataset|jeu\s+de\s+donn[eé]es|donn[eé]es)\b",
        r"\b(?:ce|le|mon)\s+dataset\s+est[- ]il\s+(?:bon|propre|fiable|correct)\b",
        r"\b(?:les|mes|ces)\s+donn[eé]es\s+sont[- ]elles\s+(?:bonnes|propres|fiables|correctes)\b",
        r"\bcomment\s+est\s+(?:la\s+)?qualit[eé]\s+(?:du|de\s+ce)\s+dataset\b",
        r"\bqu['’]y\s+a[- ]t[- ]il\s+dans\s+(?:le|ce)\s+dataset\b",
        r"\bdonne[- ]moi\s+un\s+avis\s+sur\s+(?:le|ce)\s+dataset\b",
    ),
    0.97,
),
    IntentRule(
        "capabilities",
        (
            r"\bacc[eè]s\s+[aà]\s+internet\b",
            r"\btu\s+as\s+internet\b",
            r"\bpeux[- ]tu\s+(?:aller|chercher|naviguer)\s+(?:sur\s+)?internet\b",
            r"\bpeux[- ]tu\s+chercher\s+sur\s+le\s+web\b",
            r"\bque\s+peux[- ]tu\s+faire\b",
            r"\bquelles?\s+sont\s+tes\s+capacit[eé]s\b",
            r"\btes\s+capacit[eé]s\b",
        ),
        0.98,
    ),
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
    "root_cause_analysis",
    (
        r"\broot\s+cause\b",
        r"\bcause\s+racine\b",
        r"\banalyse\s+des\s+causes\b",
        r"\bqu['’]est[- ]ce\s+qui\s+explique\s+(?:la\s+)?(?:hausse|baisse|variation|chute)\b",
        r"\bpourquoi\b.*\b(?:a\s+baiss[eé]|a\s+augment[eé]|a\s+chang[eé]|varie)\b",
        r"\bquels?\s+(?:sont\s+)?les\s+facteurs\b.*\b(?:hausse|baisse|variation)\b",
    ),
    0.95,
),
IntentRule(
    "optimize_scenarios",
    (
        r"\boptimis(?:e|er|ation)\b.*\bsc[eé]nario",
        r"\bmeilleur\s+sc[eé]nario\b",
        r"\bquel\s+sc[eé]nario\b.*\bmaximis",
        r"\bquel\s+sc[eé]nario\b.*\bminimis",
        r"\bvariables?\s+contr[oô]lables?\b",
    ),
    0.94,
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
            r"\bprofil(?:e|er|age)\b.*\bdataset\b",
        ),
        0.82,
    ),
    IntentRule(
        "conversation",
        (
            r"^(?:bonjour|bonsoir|salut|hello|hey)\b",
            r"^(?:merci|merci beaucoup)\b",
            r"\bqui\s+es[- ]tu\b",
            r"\bcomment\s+[cç]a\s+va\b",
        ),
        0.95,
    ),
)


def resolve_intent(message: str, context: AssistantContext) -> AgentIntent:
    text = message.lower().strip()
    best: AgentIntent | None = None

    for rule in RULES:
        for pattern in rule.patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                candidate = AgentIntent(
                    name=rule.name,
                    confidence=rule.confidence,
                    entities=_extract_entities(text, context),
                    rationale=f"Correspondance déterministe avec le motif: {pattern}",
                )
                if best is None or candidate.confidence > best.confidence:
                    best = candidate
                break

    if best is not None:
        return best

    # Critical v2.16.2 change:
    # an active dataset is CONTEXT, not an instruction to analyze it.
    return AgentIntent(
        name="unknown",
        confidence=0.20,
        entities=_extract_entities(text, context),
        rationale=(
            "Aucune intention fiable détectée. "
            "Le dataset actif n'est plus utilisé comme fallback d'analyse."
        ),
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

    return entities
