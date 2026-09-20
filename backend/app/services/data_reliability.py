from __future__ import annotations

import json
import math
import re
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow
from app.services.storage import get_meta, iter_dataset_metadata, load_dataframe_raw

SEVERITY_WEIGHT = {"low": 1.0, "medium": 2.0, "high": 3.0, "critical": 4.0}
BLOCKING_DEFAULT = {"high", "critical"}
SUPPORTED_RULES = {
    "required_columns", "row_count", "missing_pct", "unique", "range", "allowed_values", "dtype", "regex", "distribution_drift",
}


def _root_id(dataset_id: str) -> str:
    meta = get_meta(dataset_id)
    return str(meta.get("root_id") or meta["id"])


def _ensure_bound(workspace_id: str, dataset_id: str) -> dict[str, Any]:
    root = _root_id(dataset_id)
    row = fetch_one(
        "SELECT dataset_id FROM workspace_datasets WHERE workspace_id=:ws AND dataset_id IN (:dataset,:root)",
        {"ws": workspace_id, "dataset": dataset_id, "root": root},
    )
    if not row:
        raise PermissionError("Dataset hors du workspace actif.")
    return get_meta(dataset_id)


def _normalize_rule(raw: dict[str, Any], index: int) -> dict[str, Any]:
    rule = dict(raw or {})
    typ = str(rule.get("type") or "").strip().lower()
    if typ not in SUPPORTED_RULES:
        raise ValueError(f"Règle de contrat non supportée: {typ or '(vide)'}")
    severity = str(rule.get("severity") or "high").lower()
    if severity not in SEVERITY_WEIGHT:
        severity = "high"
    rule["type"] = typ
    rule["severity"] = severity
    rule["blocking"] = bool(rule.get("blocking", severity in BLOCKING_DEFAULT))
    rule["id"] = str(rule.get("id") or f"rule_{index+1}")
    rule["label"] = str(rule.get("label") or typ.replace("_", " ").title())[:180]
    return rule


def _decode_contract(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["rules"] = json_loads(out.pop("rules_json", None), [])
    out["enabled"] = bool(out.get("enabled"))
    out["last_score"] = None if out.get("last_score") is None else float(out["last_score"])
    return out


def save_contract(
    actor_id: str,
    workspace_id: str,
    dataset_id: str,
    *,
    name: str,
    description: str = "",
    rules: list[dict[str, Any]] | None = None,
    enforcement_mode: str = "warn",
    enabled: bool = True,
    contract_id: str | None = None,
) -> dict[str, Any]:
    meta = _ensure_bound(workspace_id, dataset_id)
    mode = str(enforcement_mode or "warn").lower()
    if mode not in {"monitor", "warn", "block"}:
        raise ValueError("enforcement_mode doit être monitor, warn ou block")
    normalized = [_normalize_rule(rule, i) for i, rule in enumerate(rules or [])]
    if not normalized:
        raise ValueError("Un contrat doit contenir au moins une règle.")
    root_id = str(meta.get("root_id") or meta["id"])
    now = utcnow()
    cid = str(contract_id or uuid.uuid4())
    existing = fetch_one("SELECT id,workspace_id,dataset_root_id,created_at,created_by FROM data_contracts WHERE id=:id", {"id": cid})
    if existing:
        if existing["workspace_id"] != workspace_id or existing["dataset_root_id"] != root_id:
            raise PermissionError("Ce contrat appartient à un autre workspace ou dataset.")
        execute(
            """UPDATE data_contracts SET dataset_id=:dataset,name=:name,description=:description,rules_json=:rules,
               enforcement_mode=:mode,enabled=:enabled,owner_user_id=:owner,updated_at=:updated WHERE id=:id""",
            {"dataset":dataset_id,"name":name.strip()[:180],"description":description.strip()[:3000],"rules":json_dumps(normalized),"mode":mode,"enabled":1 if enabled else 0,"owner":actor_id,"updated":now,"id":cid},
        )
    else:
        execute(
            """INSERT INTO data_contracts(id,workspace_id,dataset_id,dataset_root_id,name,description,rules_json,enforcement_mode,enabled,owner_user_id,status,created_by,created_at,updated_at)
               VALUES(:id,:ws,:dataset,:root,:name,:description,:rules,:mode,:enabled,:owner,'never_run',:created_by,:created,:updated)""",
            {"id":cid,"ws":workspace_id,"dataset":dataset_id,"root":root_id,"name":name.strip()[:180],"description":description.strip()[:3000],"rules":json_dumps(normalized),"mode":mode,"enabled":1 if enabled else 0,"owner":actor_id,"created_by":actor_id,"created":now,"updated":now},
        )
    return get_contract(workspace_id, cid)


def get_contract(workspace_id: str, contract_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM data_contracts WHERE id=:id AND workspace_id=:ws", {"id":contract_id,"ws":workspace_id})
    if not row:
        raise KeyError("Contrat introuvable.")
    return _decode_contract(row)


def list_contracts(workspace_id: str, dataset_id: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"ws":workspace_id}
    where = "workspace_id=:ws"
    if dataset_id:
        root = _root_id(dataset_id)
        where += " AND dataset_root_id=:root"
        params["root"] = root
    rows = fetch_all(f"SELECT * FROM data_contracts WHERE {where} ORDER BY updated_at DESC", params)
    return [_decode_contract(r) for r in rows]


def delete_contract(workspace_id: str, contract_id: str) -> None:
    get_contract(workspace_id, contract_id)
    execute("DELETE FROM data_contract_runs WHERE contract_id=:id AND workspace_id=:ws", {"id":contract_id,"ws":workspace_id})
    execute("DELETE FROM data_contracts WHERE id=:id AND workspace_id=:ws", {"id":contract_id,"ws":workspace_id})


def _dtype_family(dtype: Any) -> str:
    if pd.api.types.is_bool_dtype(dtype): return "boolean"
    if pd.api.types.is_integer_dtype(dtype): return "integer"
    if pd.api.types.is_numeric_dtype(dtype): return "numeric"
    if pd.api.types.is_datetime64_any_dtype(dtype): return "datetime"
    return "string"


def _result(rule: dict[str, Any], passed: bool, *, observed: Any = None, expected: Any = None, message: str = "", metric: float | None = None) -> dict[str, Any]:
    return {
        "rule_id": rule["id"], "type": rule["type"], "label": rule["label"], "severity": rule["severity"],
        "blocking": bool(rule.get("blocking")), "status": "pass" if passed else "fail", "observed": observed,
        "expected": expected, "message": message, "metric": metric,
    }


def _tvd(a: pd.Series, b: pd.Series) -> float:
    aa = a.astype("string").fillna("<NULL>").value_counts(normalize=True)
    bb = b.astype("string").fillna("<NULL>").value_counts(normalize=True)
    idx = aa.index.union(bb.index)
    return float(0.5 * (aa.reindex(idx, fill_value=0) - bb.reindex(idx, fill_value=0)).abs().sum())


def _numeric_ks(a: pd.Series, b: pd.Series) -> float:
    x = pd.to_numeric(a, errors="coerce").dropna().to_numpy(dtype=float)
    y = pd.to_numeric(b, errors="coerce").dropna().to_numpy(dtype=float)
    if len(x) < 2 or len(y) < 2:
        return 0.0
    try:
        from scipy.stats import ks_2samp
        return float(ks_2samp(x, y, method="auto").statistic)
    except Exception:
        grid = np.unique(np.concatenate([x, y]))
        if len(grid) == 0: return 0.0
        xs = np.sort(x); ys = np.sort(y)
        cdfx = np.searchsorted(xs, grid, side="right") / len(xs)
        cdfy = np.searchsorted(ys, grid, side="right") / len(ys)
        return float(np.max(np.abs(cdfx - cdfy)))


def _evaluate_rule(df: pd.DataFrame, rule: dict[str, Any], baseline: pd.DataFrame | None) -> dict[str, Any]:
    typ = rule["type"]
    if typ == "required_columns":
        required = [str(x) for x in rule.get("columns", [])]
        missing = [c for c in required if c not in df.columns]
        return _result(rule, not missing, observed={"missing":missing}, expected={"columns":required}, message="Toutes les colonnes requises sont présentes." if not missing else f"Colonnes manquantes: {', '.join(missing)}")
    if typ == "row_count":
        n = int(len(df)); lo = rule.get("min"); hi = rule.get("max")
        ok = (lo is None or n >= int(lo)) and (hi is None or n <= int(hi))
        return _result(rule, ok, observed=n, expected={"min":lo,"max":hi}, message=f"{n} lignes observées.", metric=float(n))
    column = str(rule.get("column") or "")
    if column not in df.columns:
        return _result(rule, False, observed="column_missing", expected=column, message=f"Colonne '{column}' absente.")
    s = df[column]
    if typ == "missing_pct":
        pct = float(s.isna().mean() * 100); max_pct = float(rule.get("max", 0))
        return _result(rule, pct <= max_pct, observed=round(pct,4), expected={"max_pct":max_pct}, message=f"{pct:.2f}% de valeurs manquantes.", metric=pct)
    if typ == "unique":
        nonnull = s.dropna(); dup_pct = float(nonnull.duplicated().mean()*100) if len(nonnull) else 0.0; max_dup=float(rule.get("max_duplicate_pct",0))
        return _result(rule, dup_pct <= max_dup, observed=round(dup_pct,4), expected={"max_duplicate_pct":max_dup}, message=f"{dup_pct:.2f}% de doublons sur {column}.", metric=dup_pct)
    if typ == "range":
        num = pd.to_numeric(s, errors="coerce"); lo=rule.get("min"); hi=rule.get("max")
        invalid = pd.Series(False, index=df.index)
        if lo is not None: invalid |= num < float(lo)
        if hi is not None: invalid |= num > float(hi)
        invalid |= (s.notna() & num.isna())
        bad=int(invalid.sum()); pct=float(bad/max(len(df),1)*100)
        return _result(rule,bad==0,observed={"invalid_rows":bad,"invalid_pct":round(pct,4)},expected={"min":lo,"max":hi},message=f"{bad} valeur(s) hors plage.",metric=pct)
    if typ == "allowed_values":
        allowed=[str(x) for x in rule.get("values",[])]; values=s.dropna().astype(str); invalid=~values.isin(allowed); bad=int(invalid.sum())
        examples=values.loc[invalid].drop_duplicates().head(5).tolist()
        return _result(rule,bad==0,observed={"invalid_rows":bad,"examples":examples},expected={"values":allowed[:100]},message=f"{bad} valeur(s) hors domaine autorisé.",metric=float(bad))
    if typ == "dtype":
        expected=str(rule.get("expected") or "string").lower(); observed=_dtype_family(s.dtype)
        ok = observed == expected or (expected == "numeric" and observed in {"integer","numeric"})
        return _result(rule,ok,observed=observed,expected=expected,message=f"Type observé: {observed}.")
    if typ == "regex":
        pattern=str(rule.get("pattern") or ""); values=s.dropna().astype(str)
        try: bad=int((~values.str.match(pattern)).sum())
        except re.error as exc: return _result(rule,False,observed="invalid_regex",expected=pattern,message=f"Regex invalide: {exc}")
        return _result(rule,bad==0,observed={"invalid_rows":bad},expected=pattern,message=f"{bad} valeur(s) non conformes.",metric=float(bad))
    if typ == "distribution_drift":
        if baseline is None or column not in baseline.columns:
            return _result(rule,False,observed="baseline_missing",expected="baseline dataset",message="Baseline de distribution indisponible.")
        if pd.api.types.is_numeric_dtype(s) and pd.api.types.is_numeric_dtype(baseline[column]):
            ks=_numeric_ks(baseline[column],s); threshold=float(rule.get("max_ks",0.2)); ok=ks<=threshold
            return _result(rule,ok,observed=round(ks,5),expected={"max_ks":threshold},message=f"KS={ks:.3f}.",metric=ks)
        tvd=_tvd(baseline[column],s); threshold=float(rule.get("max_tvd",0.2)); ok=tvd<=threshold
        return _result(rule,ok,observed=round(tvd,5),expected={"max_tvd":threshold},message=f"TVD={tvd:.3f}.",metric=tvd)
    raise ValueError(f"Règle non supportée: {typ}")


def _latest_prior_version(dataset_id: str) -> str | None:
    meta=get_meta(dataset_id); root=str(meta.get("root_id") or meta["id"]); version=int(meta.get("version",1))
    candidates=[]
    for m in iter_dataset_metadata():
        if str(m.get("root_id") or m.get("id"))==root and int(m.get("version",1))<version:
            candidates.append(m)
    candidates.sort(key=lambda x:int(x.get("version",1)),reverse=True)
    return str(candidates[0]["id"]) if candidates else None


def run_contract(actor_id: str, workspace_id: str, contract_id: str, dataset_id: str | None = None) -> dict[str, Any]:
    contract=get_contract(workspace_id,contract_id)
    target_id=str(dataset_id or contract["dataset_id"])
    meta=_ensure_bound(workspace_id,target_id)
    if str(meta.get("root_id") or meta["id"]) != str(contract["dataset_root_id"]):
        raise ValueError("Le dataset demandé n'appartient pas à la lignée du contrat.")
    df=load_dataframe_raw(target_id)
    baseline_id=_latest_prior_version(target_id)
    baseline=load_dataframe_raw(baseline_id) if baseline_id else None
    results=[_evaluate_rule(df,r,baseline) for r in contract.get("rules",[])]
    total=len(results); passed=sum(1 for r in results if r["status"]=="pass"); failed=total-passed
    blocking=sum(1 for r in results if r["status"]=="fail" and r.get("blocking"))
    weight_total=sum(SEVERITY_WEIGHT.get(r["severity"],1) for r in results) or 1
    fail_weight=sum(SEVERITY_WEIGHT.get(r["severity"],1) for r in results if r["status"]=="fail")
    score=max(0.0,round((1-fail_weight/weight_total)*100,1))
    max_failed_severity=max((SEVERITY_WEIGHT.get(r["severity"],1) for r in results if r["status"]=="fail"),default=0)
    status="healthy"
    if failed: status="warning"
    if blocking: status="critical" if max_failed_severity>=4 else "failing"
    rid=str(uuid.uuid4()); now=utcnow()
    execute(
        """INSERT INTO data_contract_runs(id,contract_id,workspace_id,dataset_id,dataset_version,status,score,checks_total,checks_passed,checks_failed,blocking_failures,results_json,baseline_dataset_id,created_by,created_at)
           VALUES(:id,:contract,:ws,:dataset,:version,:status,:score,:total,:passed,:failed,:blocking,:results,:baseline,:user,:created)""",
        {"id":rid,"contract":contract_id,"ws":workspace_id,"dataset":target_id,"version":int(meta.get("version",1)),"status":status,"score":score,"total":total,"passed":passed,"failed":failed,"blocking":blocking,"results":json_dumps(results),"baseline":baseline_id,"user":actor_id,"created":now},
    )
    execute("UPDATE data_contracts SET dataset_id=:dataset,status=:status,last_score=:score,last_run_at=:run,updated_at=:run WHERE id=:id", {"dataset":target_id,"status":status,"score":score,"run":now,"id":contract_id})
    if failed:
        severity="critical" if status=="critical" else "high" if status=="failing" else "medium"
        execute(
            """INSERT INTO reliability_events(id,workspace_id,dataset_id,event_type,severity,title,details_json,status,created_at)
               VALUES(:id,:ws,:dataset,'contract_failure',:severity,:title,:details,'open',:created)""",
            {"id":str(uuid.uuid4()),"ws":workspace_id,"dataset":target_id,"severity":severity,"title":f"Contrat {contract['name']} — {failed} contrôle(s) en échec","details":json_dumps({"contract_id":contract_id,"run_id":rid,"blocking_failures":blocking,"score":score}),"created":now},
        )
    return get_contract_run(workspace_id,rid)


def get_contract_run(workspace_id: str, run_id: str) -> dict[str, Any]:
    row=fetch_one("SELECT * FROM data_contract_runs WHERE id=:id AND workspace_id=:ws",{"id":run_id,"ws":workspace_id})
    if not row: raise KeyError("Exécution de contrat introuvable.")
    out=dict(row); out["results"]=json_loads(out.pop("results_json",None),[]); return out


def list_contract_runs(workspace_id: str, contract_id: str | None=None, dataset_id: str | None=None, limit: int=100) -> list[dict[str,Any]]:
    params:dict[str,Any]={"ws":workspace_id,"limit":max(1,min(int(limit),500))}; where="workspace_id=:ws"
    if contract_id: where+=" AND contract_id=:contract"; params["contract"]=contract_id
    if dataset_id: where+=" AND dataset_id=:dataset"; params["dataset"]=dataset_id
    rows=fetch_all(f"SELECT * FROM data_contract_runs WHERE {where} ORDER BY created_at DESC LIMIT :limit",params)
    out=[]
    for row in rows:
        item=dict(row); item["results"]=json_loads(item.pop("results_json",None),[]); out.append(item)
    return out


def register_lineage_edge(workspace_id: str, source_type: str, source_id: str, target_type: str, target_id: str, relation: str, metadata: dict[str,Any] | None=None) -> None:
    existing=fetch_one("""SELECT id FROM lineage_registry WHERE workspace_id=:ws AND source_type=:st AND source_id=:sid AND target_type=:tt AND target_id=:tid AND relation=:rel""", {"ws":workspace_id,"st":source_type,"sid":source_id,"tt":target_type,"tid":target_id,"rel":relation})
    if existing: return
    execute("""INSERT INTO lineage_registry(id,workspace_id,source_type,source_id,target_type,target_id,relation,metadata_json,created_at)
             VALUES(:id,:ws,:st,:sid,:tt,:tid,:rel,:meta,:created)""", {"id":str(uuid.uuid4()),"ws":workspace_id,"st":source_type,"sid":source_id,"tt":target_type,"tid":target_id,"rel":relation,"meta":json_dumps(metadata or {}),"created":utcnow()})


def _add_node(nodes: dict[str,dict[str,Any]], typ: str, rid: str, label: str, **meta: Any) -> str:
    key=f"{typ}:{rid}"; nodes.setdefault(key,{"id":key,"type":typ,"resource_id":rid,"label":label,**meta}); return key


def _workspace_dataset_ids(workspace_id: str) -> set[str]:
    rows=fetch_all("SELECT dataset_id FROM workspace_datasets WHERE workspace_id=:ws",{"ws":workspace_id})
    roots={str(r["dataset_id"]) for r in rows}
    ids=set()
    for meta in iter_dataset_metadata():
        if str(meta.get("root_id") or meta.get("id")) in roots or str(meta.get("id")) in roots: ids.add(str(meta.get("id")))
    return ids


def build_lineage_graph(workspace_id: str, dataset_id: str | None=None) -> dict[str,Any]:
    allowed=_workspace_dataset_ids(workspace_id)
    if dataset_id:
        _ensure_bound(workspace_id,dataset_id); root=_root_id(dataset_id)
        allowed={ds for ds in allowed if _root_id(ds)==root}
    nodes:dict[str,dict[str,Any]]={}; edges:list[dict[str,Any]]=[]; seen_edges:set[tuple[str,str,str]]=set()
    def edge(st:str,sid:str,tt:str,tid:str,rel:str,**meta:Any):
        s=f"{st}:{sid}"; t=f"{tt}:{tid}"; key=(s,t,rel)
        if key in seen_edges:return
        seen_edges.add(key);edges.append({"source":s,"target":t,"relation":rel,**meta})
    # datasets and versions
    for ds in sorted(allowed):
        try: m=get_meta(ds)
        except Exception: continue
        _add_node(nodes,"dataset",ds,str(m.get("original_name") or ds),version=int(m.get("version",1)),created_at=m.get("created_at"),root_id=m.get("root_id") or ds)
        parent=m.get("parent_id")
        if parent and parent in allowed:
            _add_node(nodes,"dataset",parent,str(get_meta(parent).get("original_name") or parent),version=int(get_meta(parent).get("version",1)))
            edge("dataset",str(parent),"dataset",ds,"transformed_to",operation=m.get("operation"))
    # connector sources + refresh history
    for src in fetch_all("SELECT id,name,dataset_id FROM connector_sources WHERE workspace_id=:ws",{"ws":workspace_id}):
        sid=str(src["id"]);_add_node(nodes,"source",sid,str(src.get("name") or sid))
        runs=fetch_all("SELECT dataset_id_after,mode,started_at FROM refresh_runs WHERE workspace_id=:ws AND source_id=:sid AND status='completed'",{"ws":workspace_id,"sid":sid})
        for r in runs:
            ds=str(r.get("dataset_id_after") or "")
            if ds and ds in allowed: edge("source",sid,"dataset",ds,"materialized_as",refresh_mode=r.get("mode"),at=r.get("started_at"))
    # analyses
    analyses_dir=get_settings().data_root/"analyses"
    if analyses_dir.exists():
        for path in analyses_dir.glob("*.json"):
            try:item=json.loads(path.read_text(encoding="utf-8"))
            except Exception:continue
            ds=str(item.get("provenance",{}).get("dataset_id") or "")
            if ds not in allowed: continue
            aid=str(item.get("session_id") or path.stem);_add_node(nodes,"analysis",aid,str(item.get("question") or "Analyse"),created_at=item.get("provenance",{}).get("executed_at"));edge("dataset",ds,"analysis",aid,"analyzed_by")
    # models
    for path in get_settings().model_dir.glob("*.card.json"):
        try:item=json.loads(path.read_text(encoding="utf-8"))
        except Exception:continue
        ds=str(item.get("dataset",{}).get("id") or "")
        if ds not in allowed:continue
        mid=str(item.get("model_id") or path.stem);_add_node(nodes,"model",mid,f"{item.get('algorithm','Model')} → {item.get('target','target')}",created_at=item.get("created_at"));edge("dataset",ds,"model",mid,"trained_model")
    # dashboards
    dashboards=get_settings().data_root/"dashboards"
    if dashboards.exists():
        for path in dashboards.glob("*.json"):
            try:item=json.loads(path.read_text(encoding="utf-8"))
            except Exception:continue
            ds=str(item.get("dataset_id") or "")
            if ds not in allowed:continue
            did=str(item.get("id") or path.stem);_add_node(nodes,"dashboard",did,str(item.get("name") or "Dashboard"),updated_at=item.get("updated_at"));edge("dataset",ds,"dashboard",did,"feeds_dashboard")
    # reports
    reports=get_settings().data_root/"reports"
    if reports.exists():
        for path in reports.glob("*.json"):
            try:item=json.loads(path.read_text(encoding="utf-8"))
            except Exception:continue
            ds=str(item.get("dataset_id") or "")
            if ds not in allowed:continue
            rid=str(item.get("id") or path.stem);_add_node(nodes,"report",rid,str(item.get("title") or "Rapport"),created_at=item.get("created_at"));edge("dataset",ds,"report",rid,"feeds_report")
            aid=str(item.get("analysis_session_id") or "")
            if aid and f"analysis:{aid}" in nodes:edge("analysis",aid,"report",rid,"included_in")
    # semantic model metrics/dimensions for this root
    semantic_dir=get_settings().data_root/"semantic"
    if semantic_dir.exists():
        roots={_root_id(ds) for ds in allowed}
        for root in roots:
            path=semantic_dir/f"{root}.json"
            if not path.exists():continue
            try:model=json.loads(path.read_text(encoding="utf-8"))
            except Exception:continue
            base_ds=next((ds for ds in allowed if _root_id(ds)==root),None)
            if not base_ds:continue
            for metric in model.get("metrics",[]):
                mid=str(metric.get("id") or "");
                if not mid:continue
                rid=f"{root}:{mid}";_add_node(nodes,"metric",rid,str(metric.get("label") or metric.get("name") or mid),certified=bool(metric.get("certified")));edge("dataset",base_ds,"metric",rid,"defines_metric")
    # explicit registry edges
    for row in fetch_all("SELECT * FROM lineage_registry WHERE workspace_id=:ws",{"ws":workspace_id}):
        st,sid,tt,tid,rel=str(row["source_type"]),str(row["source_id"]),str(row["target_type"]),str(row["target_id"]),str(row["relation"])
        _add_node(nodes,st,sid,sid);_add_node(nodes,tt,tid,tid);edge(st,sid,tt,tid,rel,metadata=json_loads(row.get("metadata_json"),{}))
    return {"nodes":list(nodes.values()),"edges":edges,"node_count":len(nodes),"edge_count":len(edges),"generated_at":utcnow()}


def impact_analysis(workspace_id: str, resource_type: str, resource_id: str, depth: int=6) -> dict[str,Any]:
    graph=build_lineage_graph(workspace_id)
    start=f"{resource_type}:{resource_id}"; node_map={n["id"]:n for n in graph["nodes"]}
    if start not in node_map: raise KeyError("Ressource absente du lineage.")
    adjacency:dict[str,list[dict[str,Any]]]={}
    for e in graph["edges"]:adjacency.setdefault(e["source"],[]).append(e)
    q=deque([(start,0)]);seen={start};impacted=[];paths=[]
    while q:
        current,d=q.popleft()
        if d>=max(1,min(depth,12)):continue
        for e in adjacency.get(current,[]):
            target=e["target"]
            paths.append({"from":current,"to":target,"relation":e["relation"],"depth":d+1})
            if target not in seen:
                seen.add(target);impacted.append({**node_map.get(target,{"id":target}),"depth":d+1,"via":e["relation"]});q.append((target,d+1))
    by_type:dict[str,int]={}
    for n in impacted:by_type[n.get("type","unknown")]=by_type.get(n.get("type","unknown"),0)+1
    return {"resource":node_map[start],"impacted":impacted,"paths":paths,"impact_count":len(impacted),"by_type":by_type,"max_depth":depth}


def publication_gate(workspace_id: str, dataset_id: str) -> dict[str,Any]:
    meta=_ensure_bound(workspace_id,dataset_id);root=str(meta.get("root_id") or meta["id"])
    contracts=list_contracts(workspace_id,dataset_id)
    blockers=[];warnings=[]
    for c in contracts:
        if not c.get("enabled"):continue
        latest = list_contract_runs(workspace_id, c["id"], limit=1)
        latest_run = latest[0] if latest else None
        state={"contract_id":c["id"],"name":c["name"],"status":c.get("status"),"score":c.get("last_score"),"enforcement_mode":c.get("enforcement_mode"),"last_dataset_id":latest_run.get("dataset_id") if latest_run else None}
        if not latest_run or str(latest_run.get("dataset_id")) != str(dataset_id):
            stale_state={**state,"reason":"current_version_not_evaluated"}
            if c.get("enforcement_mode")=="block":blockers.append(stale_state)
            else:warnings.append(stale_state)
            continue
        if c.get("status") in {"failing","critical"}:
            if c.get("enforcement_mode")=="block":blockers.append(state)
            else:warnings.append(state)
        elif c.get("status") in {"never_run",None}:warnings.append({**state,"reason":"not_evaluated"})
    # connector freshness for this lineage, if any
    freshness=[]
    for src in fetch_all("SELECT id,name,dataset_id,last_success_at,freshness_sla_minutes,status FROM connector_sources WHERE workspace_id=:ws",{"ws":workspace_id}):
        ds=src.get("dataset_id")
        if not ds:continue
        try: same=_root_id(str(ds))==root
        except Exception:same=False
        if not same:continue
        age=None;fresh="never"
        if src.get("last_success_at"):
            try:
                dt=datetime.fromisoformat(str(src["last_success_at"]).replace("Z","+00:00"));dt=dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                age=max(0,int((datetime.now(timezone.utc)-dt).total_seconds()/60));sla=int(src.get("freshness_sla_minutes") or 1440);fresh="fresh" if age<=sla else "stale"
            except Exception:pass
        item={"source_id":src["id"],"name":src["name"],"status":fresh,"age_minutes":age,"sla_minutes":int(src.get("freshness_sla_minutes") or 1440)};freshness.append(item)
        if fresh=="stale":warnings.append({"type":"freshness","source_id":src["id"],"name":src["name"],"status":"stale"})
    return {"allowed":not blockers,"dataset_id":dataset_id,"dataset_version":int(meta.get("version",1)),"blockers":blockers,"warnings":warnings,"contracts_evaluated":len(contracts),"freshness":freshness,"policy":"block only when an enabled contract in block mode has failing/critical status"}


def reliability_summary(workspace_id: str, dataset_id: str | None=None) -> dict[str,Any]:
    contracts=list_contracts(workspace_id,dataset_id)
    latest_runs=[]
    for c in contracts:
        runs=list_contract_runs(workspace_id,c["id"],limit=1)
        if runs:latest_runs.append(runs[0])
    score=round(sum(float(r.get("score") or 0) for r in latest_runs)/len(latest_runs),1) if latest_runs else None
    events=fetch_all("SELECT * FROM reliability_events WHERE workspace_id=:ws AND status='open' ORDER BY created_at DESC LIMIT 100",{"ws":workspace_id})
    for e in events:e["details"]=json_loads(e.pop("details_json",None),{})
    statuses={k:0 for k in ["healthy","warning","failing","critical","never_run"]}
    for c in contracts:statuses[c.get("status") or "never_run"]=statuses.get(c.get("status") or "never_run",0)+1
    graph=build_lineage_graph(workspace_id,dataset_id)
    return {"contracts":len(contracts),"contract_status":statuses,"reliability_score":score,"open_events":events,"open_event_count":len(events),"lineage":{"nodes":graph["node_count"],"edges":graph["edge_count"]},"generated_at":utcnow()}
