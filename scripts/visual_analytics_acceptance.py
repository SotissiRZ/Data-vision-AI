#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

CHECKS = [
    ("ranked_recommendations", "backend/app/services/visualization.py", ["score", "confidence", "rationale", "recommend_visualizations"]),
    ("advanced_chart_types", "backend/app/services/visualization.py", ["violin", "bubble", "treemap", "sankey", "map", "pca", "cluster"]),
    ("conversational_edit", "backend/app/services/visualization.py", ["edit_visualization", "Instruction d'édition", "_CHART_ALIASES"]),
    ("multi_view_composition", "backend/app/services/visualization.py", ["build_visualization_composition", "view_count", "2x2"]),
    ("visual_api", "backend/app/api/routes/datasets.py", ["/visualizations/edit", "/visualizations/compose", "VisualizationComposeRequest"]),
    ("visual_ui", "frontend/app/page.tsx", ["VISUAL ANALYTICS · NL→VIZ", "Composer 4 vues", "Modifier ce graphique en langage naturel"]),
    ("assistant_chart_contract", "backend/app/assistant/host_v212.py", ["size=size", "facet=facet", "build_visualization"]),
    ("visual_tests", "backend/tests/test_visual_analytics_v2690.py", ["test_recommendations_are_ranked_and_explained", "test_conversational_edit_changes_existing_visualization", "test_composition_builds_distinct_views"]),
]

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',default='.'); ap.add_argument('--check',action='store_true'); args=ap.parse_args(); root=Path(args.root).resolve(); results=[]
    for cid,rel,needles in CHECKS:
        p=root/rel; text=p.read_text(encoding='utf-8') if p.exists() else ''; missing=[n for n in needles if n not in text]
        results.append({'id':cid,'ok':p.exists() and not missing,'missing':missing,'path':rel})
    passed=sum(1 for r in results if r['ok'])
    payload={'product_version':(root/'VERSION').read_text(encoding='utf-8').strip(),'passed':passed,'total':len(results),'checks':results}
    (root/'compliance/VISUAL_ANALYTICS_ACCEPTANCE.json').write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f"VISUAL_ANALYTICS_ACCEPTANCE: {passed}/{len(results)}")
    for r in results: print('PASS' if r['ok'] else 'FAIL',r['id'],'' if r['ok'] else r['missing'])
    return 0 if passed==len(results) else 1

if __name__=='__main__': raise SystemExit(main())
