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
    "project_memory",
    (
        r"\bm[eé]moire\s+(?:du|de ce)\s+projet\b",
        r"\bhistorique\s+(?:analytique|des analyses|des mod[eè]les|des graphiques)\b",
        r"\bqu['’]est[- ]ce\s+que\s+tu\s+te\s+rappelles\b",
        r"\bquelles?\s+(?:sont\s+)?(?:mes|les)\s+analyses\s+pr[eé]c[eé]dentes\b",
        r"\bliste\s+(?:mes|les)\s+(?:analyses|mod[eè]les|graphiques|rapports)\s+pr[eé]c[eé]dents\b",
        r"\bretrouve\b.*\b(?:session\s+pr[eé]c[eé]dente|analyse\s+d['’]avant|mod[eè]le\s+d['’]avant)\b",
    ),
    0.999,
),

IntentRule(
    "artifact_context",
    (
        r"\b(?:ce|le|du)\s+r[eé]sultat\b",
        r"\br[eé]sultat\s+pr[eé]c[eé]dent\b",
        r"\b(?:ce|le)\s+graphique\b",
        r"\b(?:ce|le)\s+mod[eè]le\b",
        r"\b(?:ce|le)\s+rapport\b",
        r"\bcompare\b.*\bpr[eé]c[eé]dent\b",
        r"\bexplique\b.*\b(?:r[eé]sultat|graphique|mod[eè]le)\b",
        r"\brefais\b.*\bgraphique\b",
        r"\butilise\b.*\bmod[eè]le\b",
        r"\b(?:premier|premi[eè]re|deuxi[eè]me|second|seconde|troisi[eè]me|dernier|derni[eè]re|pr[eé]c[eé]dent)\s+(?:graphique|mod[eè]le|rapport|analyse|r[eé]sultat)\b",
        r"\b(?:graphique|mod[eè]le|rapport|analyse|r[eé]sultat)\s+(?:#?\d+|premier|deuxi[eè]me|troisi[eè]me|dernier|pr[eé]c[eé]dent)\b",
        r"\breprends?\b.*\b(?:analyse|r[eé]sultat|graphique|mod[eè]le|rapport)\b",
        r"\b(?:relance|relancer|r[eé]ex[eé]cute|r[eé]ex[eé]cuter|rejoue|rejouer)\b.*\b(?:analyse|artefact|r[eé]sultat|graphique|mod[eè]le|rapport)\b",
        r"\b(?:r[eé]utilise|utilise)\b.*\b(?:analyse|artefact|r[eé]sultat|graphique|mod[eè]le|rapport)\b.*\bdataset\s+actif\b",
        r"\bcompar(?:e|er|aison)\b.*\b(?:mod[eè]les?|graphiques?|rapports?|analyses?|r[eé]sultats?)\b",
        r"project-memory:[0-9a-fA-F-]{8,}",
    ),
    0.997,
),
IntentRule(
    "dataset_context",
    (
        r"\b[àa]\s+quelle\s+p[eé]riode\s+remonte\b",
        r"\bquelle\s+p[eé]riode\b.*\b(?:dataset|donn[eé]es)\b",
        r"\b(?:p[eé]riode|plage|couverture)\s+(?:temporelle|de\s+dates?)\b",
        r"\bdate\s+(?:la\s+plus\s+)?(?:ancienne|r[eé]cente)\b",
        r"\bdepuis\s+quand\b.*(?:dataset|donn[eé]es)?",
        r"\bjusqu['’]?[àa]\s+quand\b.*(?:dataset|donn[eé]es)?",
        r"\bcombien\s+de\s+(?:lignes|colonnes|variables)\b",
        r"\bquelles?\s+(?:sont\s+)?(?:les\s+)?(?:colonnes|variables)\b",
        r"\b(?:quel|quelle)\s+(?:est\s+)?(?:le\s+)?dataset\s+actif\b",
        r"\b(?:nom|version)\s+(?:du|de\s+ce|de\s+mon)\s+dataset\b",
        r"\b(?:ce|le|mon)\s+dataset\s+(?:date|remonte)\b",
    ),
    0.995,
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
        "fairness_analysis",
        (
            r"\bfairness\b",
            r"\b[eé]quit[eé]\b.*\bmod[eè]le\b",
            r"\bbiais\b.*\bmod[eè]le\b",
            r"\bperformance\b.*\bgroup",
            r"\bdisparit[eé]\b.*\bgroup",
        ),
        0.94,
    ),
    IntentRule(
        "model_risk",
        (
            r"\brisque\b.*\bmod[eè]le\b",
            r"\bmodel risk\b",
            r"\bresponsible ai\b",
        ),
        0.92,
    ),
IntentRule(
    "model_registry",
    (
        r"\bmodel\s+registry\b",
        r"\bstage\s+du\s+mod[eè]le\b",
        r"\bchampion\b.*\bchallenger\b",
        r"\bpromouvo?ir\b.*\bmod[eè]le\b",
        r"\bmettre\b.*\bproduction\b",
    ),
    0.96,
),
IntentRule(
    "monitor_model",
    (
        r"\bmonitor(?:ing|er)\b.*\bmod[eè]le\b",
        r"\bd[eé]gradation\b.*\bmod[eè]le\b",
        r"\bdrift\b.*\bmod[eè]le\b",
        r"\bperformance\b.*\bproduction\b",
    ),
    0.95,
),
IntentRule(
    "retraining_check",
    (
        r"\br[eé]entra[iî]n(?:er|ement)\b",
        r"\bretrain(?:ing)?\b",
        r"\bfaut[- ]il\b.*\br[eé]entra[iî]ner\b",
    ),
    0.94,
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
    elif re.search(r"\banomal(?:ie|ies|y)\b|\boutlier", text):
        entities["ml_task"] = "anomaly_detection"
    elif re.search(r"\bclustering\b|\bsegmentation non supervis", text):
        entities["ml_task"] = "clustering"

    time_match = re.search(r"(?:colonne\s+temporelle|date\s*column|time\s*column|date)\s*[:=]?\s*([a-zA-Z0-9_]+)", text, flags=re.IGNORECASE)
    if time_match:
        candidate = time_match.group(1)
        if candidate.lower() not in {"column", "colonne", "temporelle", "date", "time"}:
            entities["time_column"] = candidate

    return entities
