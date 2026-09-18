from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.services.connector_service import encrypt_secret, decrypt_secret
from app.services.metadata_store import execute, fetch_all, fetch_one, json_dumps, json_loads, utcnow

ALLOWED_EVENT_TYPES = {"manual", "proactive_alert", "reliability_failure", "review_approved", "certification_created"}
ALLOWED_APPROVAL_MODES = {"always", "critical_only", "none"}
ALLOWED_OPERATORS = {"eq", "neq", "in", "contains", "gt", "gte", "lt", "lte", "exists"}


def _row_destination(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["headers"] = json_loads(item.pop("headers_json", "{}"), {})
    item["enabled"] = bool(item.get("enabled"))
    item["has_secret"] = bool(item.pop("secret_ciphertext", ""))
    return item


def _row_rule(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["conditions"] = json_loads(item.pop("conditions_json", "[]"), [])
    item["quiet_hours"] = json_loads(item.pop("quiet_hours_json", None), None)
    item["payload_template"] = json_loads(item.pop("payload_template_json", "{}"), {})
    item["enabled"] = bool(item.get("enabled"))
    return item


def _row_run(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["trigger_payload"] = json_loads(item.pop("trigger_payload_json", "{}"), {})
    item["rendered_payload"] = json_loads(item.pop("rendered_payload_json", "{}"), {})
    item["approval_required"] = bool(item.get("approval_required"))
    return item


def create_destination(actor_id: str, workspace_id: str, *, name: str, webhook_url: str, secret: str = "", headers: dict[str, str] | None = None, enabled: bool = True) -> dict[str, Any]:
    _validate_webhook_url(webhook_url, resolve_dns=False)
    dest_id = str(uuid.uuid4()); now = utcnow()
    execute(
        """INSERT INTO action_destinations(id,workspace_id,name,kind,webhook_url,secret_ciphertext,headers_json,enabled,created_by,created_at,updated_at)
           VALUES(:id,:ws,:name,'webhook',:url,:secret,:headers,:enabled,:user,:now,:now)""",
        {"id": dest_id, "ws": workspace_id, "name": name.strip(), "url": webhook_url.strip(), "secret": encrypt_secret(secret),
         "headers": json_dumps(headers or {}), "enabled": 1 if enabled else 0, "user": actor_id, "now": now},
    )
    return get_destination(workspace_id, dest_id)


def get_destination(workspace_id: str, destination_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM action_destinations WHERE id=:id AND workspace_id=:ws", {"id": destination_id, "ws": workspace_id})
    if not row: raise KeyError("Destination d'action introuvable")
    return _row_destination(row)


def _get_destination_secret(workspace_id: str, destination_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM action_destinations WHERE id=:id AND workspace_id=:ws", {"id": destination_id, "ws": workspace_id})
    if not row: raise KeyError("Destination d'action introuvable")
    item = dict(row)
    item["headers"] = json_loads(item.get("headers_json"), {})
    item["secret"] = decrypt_secret(item.get("secret_ciphertext"))
    item["enabled"] = bool(item.get("enabled"))
    return item


def list_destinations(workspace_id: str) -> list[dict[str, Any]]:
    return [_row_destination(x) for x in fetch_all("SELECT * FROM action_destinations WHERE workspace_id=:ws ORDER BY updated_at DESC", {"ws": workspace_id})]


def delete_destination(workspace_id: str, destination_id: str) -> None:
    linked = fetch_one("SELECT COUNT(*) AS n FROM action_rules WHERE workspace_id=:ws AND destination_id=:id", {"ws": workspace_id, "id": destination_id}) or {"n": 0}
    if int(linked.get("n") or 0) > 0: raise ValueError("Cette destination est utilisée par une règle.")
    execute("DELETE FROM action_destinations WHERE id=:id AND workspace_id=:ws", {"id": destination_id, "ws": workspace_id})


def _validate_quiet_hours(q: dict[str, Any] | None) -> None:
    if not q or not q.get("enabled", True): return
    for key in ("start", "end"):
        raw = str(q.get(key) or "")
        try:
            hh, mm = [int(x) for x in raw.split(":", 1)]
            if not (0 <= hh <= 23 and 0 <= mm <= 59): raise ValueError
        except Exception as exc:
            raise ValueError("quiet_hours start/end doivent être au format HH:MM") from exc
    try: ZoneInfo(str(q.get("timezone") or "UTC"))
    except Exception as exc: raise ValueError("Timezone IANA invalide pour quiet_hours") from exc


def save_rule(actor_id: str, workspace_id: str, *, name: str, event_type: str, destination_id: str, conditions: list[dict[str, Any]] | None = None,
              approval_mode: str = "always", throttle_minutes: int = 15, dedupe_minutes: int = 1440, quiet_hours: dict[str, Any] | None = None,
              payload_template: dict[str, Any] | None = None, dataset_id: str | None = None, description: str = "", enabled: bool = True,
              max_retries: int = 2, retry_backoff_seconds: int = 15, rule_id: str | None = None) -> dict[str, Any]:
    if event_type not in ALLOWED_EVENT_TYPES: raise ValueError("Type d'événement d'automatisation invalide")
    if approval_mode not in ALLOWED_APPROVAL_MODES: raise ValueError("Mode d'approbation invalide")
    _ = get_destination(workspace_id, destination_id)
    for c in conditions or []:
        if str(c.get("operator") or "eq") not in ALLOWED_OPERATORS: raise ValueError(f"Opérateur invalide: {c.get('operator')}")
        if not str(c.get("field") or "").strip(): raise ValueError("Chaque condition doit définir un champ")
    _validate_quiet_hours(quiet_hours)
    now = utcnow(); throttle_minutes=max(0,min(int(throttle_minutes),10080)); dedupe_minutes=max(0,min(int(dedupe_minutes),43200))
    max_retries=max(0,min(int(max_retries),5)); retry_backoff_seconds=max(1,min(int(retry_backoff_seconds),3600))
    params={"id":rule_id or str(uuid.uuid4()),"ws":workspace_id,"name":name.strip(),"description":description.strip(),"event":event_type,"dataset":dataset_id,
            "destination":destination_id,"conditions":json_dumps(conditions or []),"approval":approval_mode,"throttle":throttle_minutes,"dedupe":dedupe_minutes,
            "quiet":json_dumps(quiet_hours) if quiet_hours else None,"template":json_dumps(payload_template or {}),"enabled":1 if enabled else 0,
            "retries":max_retries,"backoff":retry_backoff_seconds,"user":actor_id,"now":now}
    if rule_id:
        if not fetch_one("SELECT id FROM action_rules WHERE id=:id AND workspace_id=:ws", {"id":rule_id,"ws":workspace_id}): raise KeyError("Règle introuvable")
        execute("""UPDATE action_rules SET name=:name,description=:description,event_type=:event,dataset_id=:dataset,destination_id=:destination,
                   conditions_json=:conditions,approval_mode=:approval,throttle_minutes=:throttle,dedupe_minutes=:dedupe,quiet_hours_json=:quiet,
                   payload_template_json=:template,enabled=:enabled,max_retries=:retries,retry_backoff_seconds=:backoff,updated_at=:now WHERE id=:id AND workspace_id=:ws""",params)
    else:
        execute("""INSERT INTO action_rules(id,workspace_id,name,description,event_type,dataset_id,destination_id,conditions_json,approval_mode,throttle_minutes,dedupe_minutes,
                   quiet_hours_json,payload_template_json,enabled,max_retries,retry_backoff_seconds,created_by,created_at,updated_at)
                   VALUES(:id,:ws,:name,:description,:event,:dataset,:destination,:conditions,:approval,:throttle,:dedupe,:quiet,:template,:enabled,:retries,:backoff,:user,:now,:now)""",params)
    return get_rule(workspace_id, params["id"])


def get_rule(workspace_id: str, rule_id: str) -> dict[str, Any]:
    row=fetch_one("SELECT * FROM action_rules WHERE id=:id AND workspace_id=:ws",{"id":rule_id,"ws":workspace_id})
    if not row: raise KeyError("Règle d'automatisation introuvable")
    return _row_rule(row)


def list_rules(workspace_id: str) -> list[dict[str, Any]]:
    return [_row_rule(x) for x in fetch_all("SELECT * FROM action_rules WHERE workspace_id=:ws ORDER BY updated_at DESC",{"ws":workspace_id})]


def delete_rule(workspace_id: str, rule_id: str) -> None:
    execute("DELETE FROM action_rules WHERE id=:id AND workspace_id=:ws",{"id":rule_id,"ws":workspace_id})

def _value_at_path(payload: Any, path: str) -> Any:
    current=payload
    for part in [x for x in str(path).split('.') if x]:
        if isinstance(current,dict): current=current.get(part)
        elif isinstance(current,list) and part.isdigit():
            i=int(part); current=current[i] if 0<=i<len(current) else None
        else: return None
    return current


def _match_condition(payload: dict[str, Any], condition: dict[str, Any]) -> bool:
    actual=_value_at_path(payload,str(condition.get('field') or '')); op=str(condition.get('operator') or 'eq'); expected=condition.get('value')
    if op=='exists': return (actual is not None)==bool(expected if expected is not None else True)
    if op=='eq': return actual==expected
    if op=='neq': return actual!=expected
    if op=='in': return actual in (expected if isinstance(expected,list) else [expected])
    if op=='contains':
        if isinstance(actual,(list,tuple,set)): return expected in actual
        return str(expected).lower() in str(actual or '').lower()
    try:
        a,e=float(actual),float(expected)
        return {'gt':a>e,'gte':a>=e,'lt':a<e,'lte':a<=e}.get(op,False)
    except Exception: return False


def _rule_matches(rule: dict[str, Any], payload: dict[str, Any], dataset_id: str | None) -> bool:
    if rule.get('dataset_id') and str(rule.get('dataset_id'))!=str(dataset_id or ''): return False
    return all(_match_condition(payload,c) for c in rule.get('conditions') or [])


def _render_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value,dict): return {k:_render_value(v,context) for k,v in value.items()}
    if isinstance(value,list): return [_render_value(v,context) for v in value]
    if not isinstance(value,str): return value
    if value.startswith('${') and value.endswith('}') and value.count('${')==1: return _value_at_path(context,value[2:-1].strip())
    import re
    out=value
    for match in re.finditer(r'\{\{\s*([^}]+?)\s*\}\}',value):
        replacement=_value_at_path(context,match.group(1).strip())
        out=out.replace(match.group(0),'' if replacement is None else str(replacement))
    return out


def _render_payload(rule: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    meta={'event_type':event['event_type'],'event_id':event['event_id'],'workspace_id':event['workspace_id'],'dataset_id':event.get('dataset_id')}
    base={'datavision':meta,'event':event.get('payload') or {}}
    template=rule.get('payload_template') or {}
    if not template: return base
    rendered=_render_value(template,{'event':event.get('payload') or {},'meta':meta,'datavision':meta})
    return {**rendered,'_datavision':meta} if isinstance(rendered,dict) else {'payload':rendered,'_datavision':meta}


def _fingerprint(rule_id: str, event_type: str, event_id: str, payload: dict[str, Any]) -> str:
    material=json.dumps({'rule':rule_id,'event_type':event_type,'event_id':event_id,'payload':payload},sort_keys=True,ensure_ascii=False,default=str)
    return hashlib.sha256(material.encode()).hexdigest()


def _parse_iso(value: str | None) -> datetime | None:
    if not value: return None
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00')); return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception: return None


def _quiet_until(q: dict[str, Any] | None, now: datetime | None=None) -> str | None:
    if not q or not q.get('enabled',True): return None
    _validate_quiet_hours(q); tz=ZoneInfo(str(q.get('timezone') or 'UTC')); local=(now or datetime.now(timezone.utc)).astimezone(tz)
    sh,sm=[int(x) for x in str(q['start']).split(':')]; eh,em=[int(x) for x in str(q['end']).split(':')]
    start=local.replace(hour=sh,minute=sm,second=0,microsecond=0); end=local.replace(hour=eh,minute=em,second=0,microsecond=0); crosses=(sh,sm)>=(eh,em)
    inside=(local>=start or local<end) if crosses else (start<=local<end)
    if not inside: return None
    if crosses and local>=start: end=end+timedelta(days=1)
    return end.astimezone(timezone.utc).isoformat()


def _approval_required(rule: dict[str, Any], payload: dict[str, Any]) -> bool:
    mode=rule.get('approval_mode')
    return mode=='always' or (mode=='critical_only' and str(payload.get('severity') or '').lower()=='critical')


def _within_window(ts: str | None, minutes: int) -> bool:
    dt=_parse_iso(ts); return bool(dt and datetime.now(timezone.utc)-dt<=timedelta(minutes=max(0,minutes)))


def dispatch_event(actor_id: str, workspace_id: str, *, event_type: str, event_id: str | None=None, payload: dict[str, Any] | None=None,
                   dataset_id: str | None=None, enqueue: bool=True) -> dict[str, Any]:
    if event_type not in ALLOWED_EVENT_TYPES: raise ValueError('Type d’événement non supporté')
    event_id=event_id or str(uuid.uuid4()); payload=dict(payload or {})
    rules=[_row_rule(r) for r in fetch_all("SELECT * FROM action_rules WHERE workspace_id=:ws AND event_type=:event AND enabled=1 ORDER BY created_at",{'ws':workspace_id,'event':event_type})]
    created=[]; skipped=[]; event={'workspace_id':workspace_id,'event_type':event_type,'event_id':event_id,'dataset_id':dataset_id,'payload':payload}
    for rule in rules:
        if not _rule_matches(rule,payload,dataset_id): continue
        fp=_fingerprint(rule['id'],event_type,event_id,payload)
        duplicate=fetch_one("SELECT id,created_at,status FROM action_runs WHERE workspace_id=:ws AND rule_id=:rule AND fingerprint=:fp ORDER BY created_at DESC LIMIT 1",{'ws':workspace_id,'rule':rule['id'],'fp':fp})
        if duplicate and _within_window(duplicate.get('created_at'),int(rule.get('dedupe_minutes') or 0)):
            skipped.append({'rule_id':rule['id'],'reason':'dedupe','existing_run_id':duplicate['id']}); continue
        last=fetch_one("SELECT id,created_at FROM action_runs WHERE workspace_id=:ws AND rule_id=:rule AND status NOT IN ('suppressed_dedupe','suppressed_throttle') ORDER BY created_at DESC LIMIT 1",{'ws':workspace_id,'rule':rule['id']})
        approval=_approval_required(rule,payload); status='pending_approval' if approval else 'queued'; scheduled_for=None
        if last and int(rule.get('throttle_minutes') or 0)>0 and _within_window(last.get('created_at'),int(rule['throttle_minutes'])): status='suppressed_throttle'
        elif status!='pending_approval':
            scheduled_for=_quiet_until(rule.get('quiet_hours'))
            if scheduled_for: status='scheduled'
        run_id=str(uuid.uuid4()); now=utcnow(); rendered=_render_payload(rule,event)
        execute("""INSERT INTO action_runs(id,workspace_id,rule_id,destination_id,event_type,event_id,dataset_id,status,fingerprint,trigger_payload_json,rendered_payload_json,
                   approval_required,requested_by,scheduled_for,attempt_count,created_at,updated_at)
                   VALUES(:id,:ws,:rule,:dest,:event,:eventid,:dataset,:status,:fp,:trigger,:rendered,:approval,:user,:scheduled,0,:now,:now)""",
                {'id':run_id,'ws':workspace_id,'rule':rule['id'],'dest':rule['destination_id'],'event':event_type,'eventid':event_id,'dataset':dataset_id,
                 'status':status,'fp':fp,'trigger':json_dumps(payload),'rendered':json_dumps(rendered),'approval':1 if approval else 0,'user':actor_id,'scheduled':scheduled_for,'now':now})
        execute("UPDATE action_rules SET last_triggered_at=:now WHERE id=:id",{'now':now,'id':rule['id']})
        run=get_run(workspace_id,run_id); created.append(run)
        if enqueue and status=='queued': _enqueue_run(run,rule)
    return {'event_id':event_id,'event_type':event_type,'matched_rules':len(created)+len(skipped),'runs':created,'skipped':skipped}

def _enqueue_run(run: dict[str, Any], rule: dict[str, Any] | None=None) -> None:
    from app.services.job_service import submit_job
    if run.get('status') not in {'queued','approved'}: return
    rule=rule or get_rule(run['workspace_id'],run['rule_id'])
    ws=fetch_one("SELECT organization_id FROM workspaces WHERE id=:id",{'id':run['workspace_id']}) or {}
    job=submit_job(user_id=run.get('approved_by') or run.get('requested_by') or rule.get('created_by'),organization_id=ws.get('organization_id'),
                   workspace_id=run['workspace_id'],job_type='action_delivery',dataset_id=run.get('dataset_id'),payload={'action_run_id':run['id']},
                   max_retries=int(rule.get('max_retries') or 2),retry_backoff_seconds=int(rule.get('retry_backoff_seconds') or 15))
    execute("UPDATE action_runs SET job_id=:job,status='queued',updated_at=:now WHERE id=:id",{'job':job['id'],'now':utcnow(),'id':run['id']})


def get_run(workspace_id: str, run_id: str) -> dict[str, Any]:
    row=fetch_one("SELECT * FROM action_runs WHERE id=:id AND workspace_id=:ws",{'id':run_id,'ws':workspace_id})
    if not row: raise KeyError("Exécution d'action introuvable")
    item=_row_run(row); item['attempts']=fetch_all("SELECT * FROM action_delivery_attempts WHERE run_id=:run ORDER BY attempt_number",{'run':run_id}); return item


def list_runs(workspace_id: str, status: str | None=None, limit: int=200) -> list[dict[str, Any]]:
    params={'ws':workspace_id,'limit':max(1,min(int(limit),500))}; where='workspace_id=:ws'
    if status and status!='all': where+=' AND status=:status'; params['status']=status
    return [_row_run(x) for x in fetch_all(f"SELECT * FROM action_runs WHERE {where} ORDER BY created_at DESC LIMIT :limit",params)]


def approve_run(actor_id: str, workspace_id: str, run_id: str, note: str='') -> dict[str, Any]:
    run=get_run(workspace_id,run_id)
    if run['status']!='pending_approval': raise ValueError("Cette action n'est pas en attente d'approbation")
    rule=get_rule(workspace_id,run['rule_id']); scheduled=_quiet_until(rule.get('quiet_hours')); status='scheduled' if scheduled else 'approved'; now=utcnow()
    execute("UPDATE action_runs SET status=:status,approved_by=:user,approval_note=:note,approved_at=:at,scheduled_for=:scheduled,updated_at=:at WHERE id=:id AND workspace_id=:ws",
            {'status':status,'user':actor_id,'note':note.strip(),'at':now,'scheduled':scheduled,'id':run_id,'ws':workspace_id})
    updated=get_run(workspace_id,run_id)
    if status=='approved': _enqueue_run(updated,rule); updated=get_run(workspace_id,run_id)
    return updated


def reject_run(actor_id: str, workspace_id: str, run_id: str, note: str='') -> dict[str, Any]:
    run=get_run(workspace_id,run_id)
    if run['status']!='pending_approval': raise ValueError("Cette action n'est pas en attente d'approbation")
    now=utcnow(); execute("UPDATE action_runs SET status='rejected',approved_by=:user,approval_note=:note,approved_at=:at,finished_at=:at,updated_at=:at WHERE id=:id AND workspace_id=:ws",
                         {'user':actor_id,'note':note.strip(),'at':now,'id':run_id,'ws':workspace_id}); return get_run(workspace_id,run_id)


def replay_run(actor_id: str, workspace_id: str, run_id: str) -> dict[str, Any]:
    original=get_run(workspace_id,run_id); rule=get_rule(workspace_id,original['rule_id']); new_id=str(uuid.uuid4()); now=utcnow(); scheduled=_quiet_until(rule.get('quiet_hours')); status='scheduled' if scheduled else 'approved'
    execute("""INSERT INTO action_runs(id,workspace_id,rule_id,destination_id,event_type,event_id,dataset_id,status,fingerprint,trigger_payload_json,rendered_payload_json,
               approval_required,requested_by,approved_by,approval_note,approved_at,scheduled_for,attempt_count,replay_of,created_at,updated_at)
               VALUES(:id,:ws,:rule,:dest,:event,:eventid,:dataset,:status,:fp,:trigger,:rendered,0,:user,:user,'Replay manuel gouverné',:now,:scheduled,0,:replay,:now,:now)""",
            {'id':new_id,'ws':workspace_id,'rule':original['rule_id'],'dest':original['destination_id'],'event':original['event_type'],'eventid':f"replay:{original['event_id']}:{new_id}",
             'dataset':original.get('dataset_id'),'status':status,'fp':hashlib.sha256(f"replay:{original['fingerprint']}:{new_id}".encode()).hexdigest(),
             'trigger':json_dumps(original.get('trigger_payload') or {}),'rendered':json_dumps(original.get('rendered_payload') or {}),'user':actor_id,'now':now,'scheduled':scheduled,'replay':run_id})
    run=get_run(workspace_id,new_id)
    if status=='approved': _enqueue_run(run,rule); run=get_run(workspace_id,new_id)
    return run


def _validate_webhook_url(url: str, *, resolve_dns: bool=True) -> None:
    parsed=urlparse(url.strip())
    if parsed.scheme not in {'https','http'} or not parsed.hostname: raise ValueError('Webhook URL invalide')
    dev_local=get_settings().app_env=='development' and parsed.scheme=='http' and parsed.hostname in {'localhost','127.0.0.1','::1'}
    if parsed.scheme!='https' and not dev_local: raise ValueError('Les webhooks doivent utiliser HTTPS hors localhost en développement')
    if parsed.username or parsed.password: raise ValueError("Les credentials dans l'URL webhook sont interdits")
    if resolve_dns and not dev_local:
        try:
            infos=socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=='https' else 80),type=socket.SOCK_STREAM)
            for info in infos:
                ip=ipaddress.ip_address(info[4][0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    raise ValueError('Webhook vers une adresse réseau privée/réservée refusé')
        except socket.gaierror as exc: raise ValueError('Résolution DNS du webhook impossible') from exc


def _post_webhook(destination: dict[str, Any], body: bytes, headers: dict[str,str], timeout: float=10.0) -> tuple[int,str]:
    _validate_webhook_url(destination['webhook_url'],resolve_dns=True); req=Request(destination['webhook_url'],data=body,headers=headers,method='POST')
    try:
        with urlopen(req,timeout=timeout) as response: return int(response.status),response.read(8192).decode('utf-8',errors='replace')
    except HTTPError as exc:
        raw=exc.read(8192).decode('utf-8',errors='replace') if getattr(exc,'fp',None) else str(exc); return int(exc.code),raw
    except URLError as exc: raise RuntimeError(f"Webhook inaccessible: {exc.reason}") from exc


def execute_action_run(run_id: str) -> dict[str, Any]:
    row=fetch_one("SELECT workspace_id FROM action_runs WHERE id=:id",{'id':run_id})
    if not row: raise KeyError("Exécution d'action introuvable")
    ws=row['workspace_id']; run=get_run(ws,run_id)
    if run['status'] in {'completed','rejected','cancelled'}: return run
    if run['status']=='pending_approval': raise PermissionError('Approbation humaine requise avant exécution')
    if run['status']=='scheduled':
        due=_parse_iso(run.get('scheduled_for'))
        if due and due>datetime.now(timezone.utc): raise RuntimeError('Action planifiée pour une exécution ultérieure')
    destination=_get_destination_secret(ws,run['destination_id'])
    if not destination.get('enabled'): raise RuntimeError('Destination désactivée')
    count=fetch_one("SELECT COUNT(*) AS n FROM action_delivery_attempts WHERE run_id=:run",{'run':run_id}) or {'n':0}; attempt=int(count.get('n') or 0)+1
    attempt_id=str(uuid.uuid4()); started=utcnow(); perf=time.perf_counter()
    execute("INSERT INTO action_delivery_attempts(id,run_id,workspace_id,attempt_number,status,created_at) VALUES(:id,:run,:ws,:n,'running',:at)",{'id':attempt_id,'run':run_id,'ws':ws,'n':attempt,'at':started})
    execute("UPDATE action_runs SET status='running',started_at=COALESCE(started_at,:at),attempt_count=:n,updated_at=:at WHERE id=:id",{'at':started,'n':attempt,'id':run_id})
    body=json.dumps(run.get('rendered_payload') or {},ensure_ascii=False,separators=(',',':'),default=str).encode(); ts=str(int(time.time())); secret=str(destination.get('secret') or '')
    signature=hmac.new(secret.encode(),f'{ts}.'.encode()+body,hashlib.sha256).hexdigest() if secret else ''
    headers={'Content-Type':'application/json','User-Agent':'DataVision-Actions/2.10','X-DataVision-Timestamp':ts,'X-DataVision-Run-ID':run_id,'Idempotency-Key':run['fingerprint']}
    if signature: headers['X-DataVision-Signature']=f'v1={signature}'
    for k,v in (destination.get('headers') or {}).items():
        if str(k).lower() not in {'host','content-length','x-datavision-signature','x-datavision-timestamp','idempotency-key'}: headers[str(k)]=str(v)
    try:
        code,response=_post_webhook(destination,body,headers); latency=(time.perf_counter()-perf)*1000; ok=200<=code<300; finished=utcnow()
        execute("UPDATE action_delivery_attempts SET status=:status,response_code=:code,response_body=:body,latency_ms=:latency,finished_at=:at WHERE id=:id",
                {'status':'completed' if ok else 'failed','code':code,'body':response[:8000],'latency':latency,'at':finished,'id':attempt_id})
        if not ok:
            execute("UPDATE action_runs SET status='failed',last_response_code=:code,last_response_body=:body,error=:error,updated_at=:at WHERE id=:id",{'code':code,'body':response[:8000],'error':f'Webhook HTTP {code}','at':finished,'id':run_id}); raise RuntimeError(f'Webhook HTTP {code}')
        execute("UPDATE action_runs SET status='completed',last_response_code=:code,last_response_body=:body,error=NULL,finished_at=:at,updated_at=:at WHERE id=:id",{'code':code,'body':response[:8000],'at':finished,'id':run_id})
    except Exception as exc:
        latency=(time.perf_counter()-perf)*1000; finished=utcnow()
        execute("UPDATE action_delivery_attempts SET status='failed',error=:error,latency_ms=:latency,finished_at=:at WHERE id=:id",{'error':str(exc)[:8000],'latency':latency,'at':finished,'id':attempt_id})
        execute("UPDATE action_runs SET status='failed',error=:error,updated_at=:at WHERE id=:id",{'error':str(exc)[:8000],'at':finished,'id':run_id}); raise
    return get_run(ws,run_id)

def process_due_runs(limit: int=50) -> int:
    now=utcnow(); rows=fetch_all("SELECT id,workspace_id,rule_id FROM action_runs WHERE status='scheduled' AND scheduled_for IS NOT NULL AND scheduled_for<=:now ORDER BY scheduled_for LIMIT :limit",{'now':now,'limit':max(1,min(limit,200))}); count=0
    for row in rows:
        try:
            execute("UPDATE action_runs SET status='approved',updated_at=:now WHERE id=:id AND status='scheduled'",{'now':now,'id':row['id']})
            run=get_run(row['workspace_id'],row['id'])
            if run['status']=='approved': _enqueue_run(run,get_rule(row['workspace_id'],row['rule_id'])); count+=1
        except Exception: continue
    return count


def action_summary(workspace_id: str) -> dict[str, Any]:
    counts=fetch_all("SELECT status,COUNT(*) AS n FROM action_runs WHERE workspace_id=:ws GROUP BY status",{'ws':workspace_id}); status_counts={str(x['status']):int(x['n']) for x in counts}
    completed=status_counts.get('completed',0); failed=status_counts.get('failed',0); rules=list_rules(workspace_id)
    return {'destinations':len(list_destinations(workspace_id)),'rules':len(rules),'active_rules':sum(1 for r in rules if r.get('enabled')),
            'runs':sum(status_counts.values()),'completed':completed,'failed':failed,'pending_approval':status_counts.get('pending_approval',0),'scheduled':status_counts.get('scheduled',0),
            'delivery_success_pct':round(100.0*completed/max(completed+failed,1),2) if completed+failed else None,'status_counts':status_counts,
            'security':{'signed_webhooks':True,'ssrf_guard':True,'idempotency_keys':True,'human_approval':True}}

# ============================================================================
# DataVision AI v2.11 — Enterprise Action Connectors & staged approvals
# These definitions intentionally override the v2.10 primitives above while
# preserving their public API for backwards compatibility.
# ============================================================================
import base64 as _b64mod
import smtplib as _smtplib
from email.message import EmailMessage as _EmailMessage
from urllib.parse import urlencode as _urlencode

_NATIVE_DESTINATION_KINDS = {"webhook", "slack", "teams", "jira", "email"}
_CREDENTIAL_TYPES = {"none", "hmac", "bearer", "basic", "oauth2_client_credentials", "smtp"}
_APPROVAL_ROLES = {"owner", "admin", "data_scientist", "analyst"}
ALLOWED_APPROVAL_MODES = {"always", "critical_only", "none", "chain"}


def _destination_options(workspace_id: str, destination_id: str, *, with_secret: bool = False) -> dict[str, Any]:
    row = fetch_one(
        "SELECT * FROM action_destination_options WHERE destination_id=:id AND workspace_id=:ws",
        {"id": destination_id, "ws": workspace_id},
    )
    if not row:
        return {"config": {}, "credential_type": "none", "oauth": {}, "credential": {}}
    credential: dict[str, Any] = {}
    if with_secret and row.get("credential_ciphertext"):
        raw = decrypt_secret(row.get("credential_ciphertext"))
        credential = json_loads(raw, {}) if raw else {}
    return {
        "config": json_loads(row.get("config_json"), {}),
        "credential_type": row.get("credential_type") or "none",
        "oauth": json_loads(row.get("oauth_json"), {}),
        "credential": credential,
        "has_credential": bool(row.get("credential_ciphertext")),
    }


def _row_destination(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    raw_headers = json_loads(item.pop("headers_json", "{}"), {})
    item["headers"] = {str(k): ("***" if any(x in str(k).lower() for x in ("authorization","token","secret","api-key","apikey","cookie")) else str(v)) for k,v in raw_headers.items()}
    item["enabled"] = bool(item.get("enabled"))
    item["has_secret"] = bool(item.pop("secret_ciphertext", ""))
    opts = _destination_options(str(item["workspace_id"]), str(item["id"]), with_secret=False)
    raw_config = opts["config"]
    kind = str(item.get("kind") or "webhook")
    if kind == "email":
        item["config"] = {"smtp_port": raw_config.get("smtp_port"), "starttls": raw_config.get("starttls", True), "ssl": raw_config.get("ssl", False), "recipient_count": len(raw_config.get("to") or [])}
        item["webhook_url"] = "smtp://configured"
    elif kind == "slack":
        item["config"] = {"mode": raw_config.get("mode", "webhook"), "channel": raw_config.get("channel")}
        if raw_config.get("mode", "webhook") == "webhook": item["webhook_url"] = "https://slack-webhook/configured"
    elif kind == "teams":
        item["config"] = {}
        item["webhook_url"] = "https://teams-workflow/configured"
    elif kind == "webhook":
        item["config"] = {}
        item["webhook_url"] = "https://webhook/configured"
    else:
        item["config"] = raw_config
    item["credential_type"] = opts["credential_type"]
    oauth = opts["oauth"]
    item["oauth"] = {"configured": bool(oauth.get("token_url")), "scope": oauth.get("scope") or ""} if oauth else {}
    item["has_credential"] = opts["has_credential"]
    return item


def _get_destination_secret(workspace_id: str, destination_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM action_destinations WHERE id=:id AND workspace_id=:ws", {"id": destination_id, "ws": workspace_id})
    if not row:
        raise KeyError("Destination d'action introuvable")
    item = dict(row)
    item["headers"] = json_loads(item.get("headers_json"), {})
    item["secret"] = decrypt_secret(item.get("secret_ciphertext"))
    item["enabled"] = bool(item.get("enabled"))
    item.update(_destination_options(workspace_id, destination_id, with_secret=True))
    encrypted_endpoint = (item.get("credential") or {}).get("_endpoint")
    if encrypted_endpoint:
        item["webhook_url"] = encrypted_endpoint
    return item


def _validate_native_destination(kind: str, webhook_url: str, config: dict[str, Any], credential_type: str, credential: dict[str, Any], oauth: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    kind = str(kind or "webhook").lower().strip()
    if kind not in _NATIVE_DESTINATION_KINDS:
        raise ValueError("Type de destination non supporté")
    if credential_type not in _CREDENTIAL_TYPES:
        raise ValueError("Type de credential non supporté")
    config = dict(config or {})
    endpoint = (webhook_url or "").strip()
    if kind == "webhook":
        if not endpoint:
            raise ValueError("URL webhook requise")
        _validate_webhook_url(endpoint, resolve_dns=False)
    elif kind == "slack":
        mode = str(config.get("mode") or ("api" if credential_type in {"bearer", "oauth2_client_credentials"} else "webhook")).lower()
        if mode not in {"webhook", "api"}:
            raise ValueError("Slack mode doit être webhook ou api")
        config["mode"] = mode
        if mode == "webhook":
            if not endpoint:
                raise ValueError("URL Incoming Webhook Slack requise")
            _validate_webhook_url(endpoint, resolve_dns=False)
        else:
            endpoint = endpoint or "https://slack.com/api/chat.postMessage"
            _validate_webhook_url(endpoint, resolve_dns=False)
            if credential_type not in {"bearer", "oauth2_client_credentials"}:
                raise ValueError("Slack API exige un token Bearer ou OAuth2")
            if not config.get("channel"):
                raise ValueError("Canal Slack requis en mode API")
    elif kind == "teams":
        if not endpoint:
            raise ValueError("URL Microsoft Teams Workflow/Webhook requise")
        _validate_webhook_url(endpoint, resolve_dns=False)
    elif kind == "jira":
        if not endpoint:
            raise ValueError("URL de base Jira requise")
        _validate_webhook_url(endpoint, resolve_dns=False)
        endpoint = endpoint.rstrip("/")
        if credential_type not in {"basic", "bearer", "oauth2_client_credentials"}:
            raise ValueError("Jira exige Basic, Bearer ou OAuth2")
        if not config.get("project_key"):
            raise ValueError("Clé de projet Jira requise")
        config.setdefault("issue_type", "Task")
    elif kind == "email":
        host = str(config.get("smtp_host") or "").strip()
        port = int(config.get("smtp_port") or (465 if config.get("ssl") else 587))
        if not host or not 1 <= port <= 65535:
            raise ValueError("Serveur SMTP/port invalides")
        if not config.get("from_email"):
            raise ValueError("Adresse expéditeur requise")
        recipients = config.get("to") or []
        if isinstance(recipients, str):
            recipients = [x.strip() for x in recipients.split(",") if x.strip()]
        config["to"] = recipients
        config["smtp_port"] = port
        endpoint = f"smtp://{host}:{port}"
        if credential_type not in {"none", "smtp", "oauth2_client_credentials"}:
            raise ValueError("Email supporte SMTP ou OAuth2")
    if credential_type == "bearer" and not str(credential.get("token") or "").strip():
        raise ValueError("Token Bearer requis")
    if credential_type == "basic" and not (credential.get("username") and (credential.get("password") or credential.get("api_token"))):
        raise ValueError("Credential Basic incomplet")
    if credential_type == "smtp" and not credential.get("username"):
        raise ValueError("Utilisateur SMTP requis")
    if credential_type == "oauth2_client_credentials":
        if not (credential.get("client_id") and credential.get("client_secret") and oauth.get("token_url")):
            raise ValueError("OAuth2 client_credentials exige client_id, client_secret et token_url")
        _validate_webhook_url(str(oauth["token_url"]), resolve_dns=False)
    return endpoint, config


def create_destination(actor_id: str, workspace_id: str, *, name: str, webhook_url: str = "", secret: str = "", headers: dict[str, str] | None = None,
                       enabled: bool = True, kind: str = "webhook", config: dict[str, Any] | None = None, credential_type: str = "none",
                       credential: dict[str, Any] | None = None, oauth: dict[str, Any] | None = None) -> dict[str, Any]:
    config = dict(config or {})
    credential = dict(credential or {})
    oauth = dict(oauth or {})
    # Backwards-compatible webhook secret becomes HMAC if no explicit profile was supplied.
    if kind == "webhook" and secret and credential_type == "none":
        credential_type = "hmac"
    endpoint, config = _validate_native_destination(kind, webhook_url, config, credential_type, credential, oauth)
    dest_id = str(uuid.uuid4())
    now = utcnow()
    stored_credential = dict(credential)
    sensitive_endpoint = kind in {"webhook", "teams"} or (kind == "slack" and config.get("mode") == "webhook")
    stored_url = endpoint
    if sensitive_endpoint:
        stored_credential["_endpoint"] = endpoint
        stored_url = f"encrypted://{kind}-endpoint"
    execute(
        """INSERT INTO action_destinations(id,workspace_id,name,kind,webhook_url,secret_ciphertext,headers_json,enabled,created_by,created_at,updated_at)
           VALUES(:id,:ws,:name,:kind,:url,:secret,:headers,:enabled,:user,:now,:now)""",
        {"id": dest_id, "ws": workspace_id, "name": name.strip(), "kind": kind, "url": stored_url, "secret": encrypt_secret(secret),
         "headers": json_dumps(headers or {}), "enabled": 1 if enabled else 0, "user": actor_id, "now": now},
    )
    execute(
        """INSERT INTO action_destination_options(destination_id,workspace_id,config_json,credential_type,credential_ciphertext,oauth_json,created_at,updated_at)
           VALUES(:id,:ws,:config,:ctype,:credential,:oauth,:now,:now)""",
        {"id": dest_id, "ws": workspace_id, "config": json_dumps(config), "ctype": credential_type,
         "credential": encrypt_secret(json_dumps(stored_credential)) if stored_credential else "", "oauth": json_dumps(oauth), "now": now},
    )
    return get_destination(workspace_id, dest_id)


def get_destination(workspace_id: str, destination_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM action_destinations WHERE id=:id AND workspace_id=:ws", {"id": destination_id, "ws": workspace_id})
    if not row:
        raise KeyError("Destination d'action introuvable")
    return _row_destination(row)


def list_destinations(workspace_id: str) -> list[dict[str, Any]]:
    return [_row_destination(x) for x in fetch_all("SELECT * FROM action_destinations WHERE workspace_id=:ws ORDER BY updated_at DESC", {"ws": workspace_id})]


def delete_destination(workspace_id: str, destination_id: str) -> None:
    linked = fetch_one("SELECT COUNT(*) AS n FROM action_rules WHERE workspace_id=:ws AND destination_id=:id", {"ws": workspace_id, "id": destination_id}) or {"n": 0}
    if int(linked.get("n") or 0) > 0:
        raise ValueError("Cette destination est utilisée par une règle.")
    execute("DELETE FROM action_destination_options WHERE destination_id=:id AND workspace_id=:ws", {"id": destination_id, "ws": workspace_id})
    execute("DELETE FROM action_destinations WHERE id=:id AND workspace_id=:ws", {"id": destination_id, "ws": workspace_id})


def _normalize_approval_chain(steps: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, raw in enumerate(steps or []):
        role = str(raw.get("role") or "").strip() or None
        user_id = str(raw.get("user_id") or "").strip() or None
        if role and role not in _APPROVAL_ROLES:
            raise ValueError(f"Rôle d'approbation invalide: {role}")
        if not role and not user_id:
            raise ValueError("Chaque étape d'approbation doit cibler un rôle ou un utilisateur")
        out.append({"order": idx + 1, "label": str(raw.get("label") or f"Étape {idx+1}")[:160], "role": role, "user_id": user_id})
    if len(out) > 6:
        raise ValueError("Une chaîne d'approbation est limitée à 6 étapes")
    return out


def _approval_chain_for_rule(workspace_id: str, rule_id: str) -> list[dict[str, Any]]:
    row = fetch_one("SELECT steps_json FROM action_rule_approval_chains WHERE rule_id=:id AND workspace_id=:ws", {"id": rule_id, "ws": workspace_id})
    return json_loads(row.get("steps_json"), []) if row else []


def _row_rule(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["conditions"] = json_loads(item.pop("conditions_json", "[]"), [])
    item["quiet_hours"] = json_loads(item.pop("quiet_hours_json", None), None)
    item["payload_template"] = json_loads(item.pop("payload_template_json", "{}"), {})
    item["enabled"] = bool(item.get("enabled"))
    item["approval_chain"] = _approval_chain_for_rule(str(item["workspace_id"]), str(item["id"]))
    return item


def save_rule(actor_id: str, workspace_id: str, *, name: str, event_type: str, destination_id: str, conditions: list[dict[str, Any]] | None = None,
              approval_mode: str = "always", throttle_minutes: int = 15, dedupe_minutes: int = 1440, quiet_hours: dict[str, Any] | None = None,
              payload_template: dict[str, Any] | None = None, dataset_id: str | None = None, description: str = "", enabled: bool = True,
              max_retries: int = 2, retry_backoff_seconds: int = 15, rule_id: str | None = None,
              approval_chain: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError("Type d'événement d'automatisation invalide")
    if approval_mode not in ALLOWED_APPROVAL_MODES:
        raise ValueError("Mode d'approbation invalide")
    _ = get_destination(workspace_id, destination_id)
    chain = _normalize_approval_chain(approval_chain)
    if approval_mode == "chain" and not chain:
        raise ValueError("Le mode chain exige au moins une étape d'approbation")
    for c in conditions or []:
        if str(c.get("operator") or "eq") not in ALLOWED_OPERATORS:
            raise ValueError(f"Opérateur invalide: {c.get('operator')}")
        if not str(c.get("field") or "").strip():
            raise ValueError("Chaque condition doit définir un champ")
    _validate_quiet_hours(quiet_hours)
    now = utcnow()
    throttle_minutes = max(0, min(int(throttle_minutes), 10080))
    dedupe_minutes = max(0, min(int(dedupe_minutes), 43200))
    max_retries = max(0, min(int(max_retries), 5))
    retry_backoff_seconds = max(1, min(int(retry_backoff_seconds), 3600))
    params = {"id": rule_id or str(uuid.uuid4()), "ws": workspace_id, "name": name.strip(), "description": description.strip(), "event": event_type,
              "dataset": dataset_id, "destination": destination_id, "conditions": json_dumps(conditions or []), "approval": approval_mode,
              "throttle": throttle_minutes, "dedupe": dedupe_minutes, "quiet": json_dumps(quiet_hours) if quiet_hours else None,
              "template": json_dumps(payload_template or {}), "enabled": 1 if enabled else 0, "retries": max_retries,
              "backoff": retry_backoff_seconds, "user": actor_id, "now": now}
    if rule_id:
        if not fetch_one("SELECT id FROM action_rules WHERE id=:id AND workspace_id=:ws", {"id": rule_id, "ws": workspace_id}):
            raise KeyError("Règle introuvable")
        execute("""UPDATE action_rules SET name=:name,description=:description,event_type=:event,dataset_id=:dataset,destination_id=:destination,
                   conditions_json=:conditions,approval_mode=:approval,throttle_minutes=:throttle,dedupe_minutes=:dedupe,quiet_hours_json=:quiet,
                   payload_template_json=:template,enabled=:enabled,max_retries=:retries,retry_backoff_seconds=:backoff,updated_at=:now WHERE id=:id AND workspace_id=:ws""", params)
    else:
        execute("""INSERT INTO action_rules(id,workspace_id,name,description,event_type,dataset_id,destination_id,conditions_json,approval_mode,throttle_minutes,dedupe_minutes,
                   quiet_hours_json,payload_template_json,enabled,max_retries,retry_backoff_seconds,created_by,created_at,updated_at)
                   VALUES(:id,:ws,:name,:description,:event,:dataset,:destination,:conditions,:approval,:throttle,:dedupe,:quiet,:template,:enabled,:retries,:backoff,:user,:now,:now)""", params)
    execute("DELETE FROM action_rule_approval_chains WHERE rule_id=:id AND workspace_id=:ws", {"id": params["id"], "ws": workspace_id})
    if chain:
        execute("""INSERT INTO action_rule_approval_chains(rule_id,workspace_id,steps_json,created_at,updated_at)
                   VALUES(:id,:ws,:steps,:now,:now)""", {"id": params["id"], "ws": workspace_id, "steps": json_dumps(chain), "now": now})
    return get_rule(workspace_id, params["id"])


def get_rule(workspace_id: str, rule_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM action_rules WHERE id=:id AND workspace_id=:ws", {"id": rule_id, "ws": workspace_id})
    if not row:
        raise KeyError("Règle d'automatisation introuvable")
    return _row_rule(row)


def list_rules(workspace_id: str) -> list[dict[str, Any]]:
    return [_row_rule(x) for x in fetch_all("SELECT * FROM action_rules WHERE workspace_id=:ws ORDER BY updated_at DESC", {"ws": workspace_id})]


def delete_rule(workspace_id: str, rule_id: str) -> None:
    execute("DELETE FROM action_rule_approval_chains WHERE rule_id=:id AND workspace_id=:ws", {"id": rule_id, "ws": workspace_id})
    execute("DELETE FROM action_rules WHERE id=:id AND workspace_id=:ws", {"id": rule_id, "ws": workspace_id})


def _approval_required(rule: dict[str, Any], payload: dict[str, Any]) -> bool:
    mode = rule.get("approval_mode")
    return mode in {"always", "chain"} or (mode == "critical_only" and str(payload.get("severity") or "").lower() == "critical")


def _create_run_approval_steps(run_id: str, workspace_id: str, rule: dict[str, Any]) -> None:
    chain = rule.get("approval_chain") or []
    now = utcnow()
    for step in chain:
        execute(
            """INSERT INTO action_approval_steps(id,run_id,workspace_id,step_order,label,required_role,required_user_id,status,created_at)
               VALUES(:id,:run,:ws,:ord,:label,:role,:user,'pending',:now)""",
            {"id": str(uuid.uuid4()), "run": run_id, "ws": workspace_id, "ord": int(step.get("order") or 1), "label": step.get("label") or "Approval",
             "role": step.get("role"), "user": step.get("user_id"), "now": now},
        )


def dispatch_event(actor_id: str, workspace_id: str, *, event_type: str, event_id: str | None = None, payload: dict[str, Any] | None = None,
                   dataset_id: str | None = None, enqueue: bool = True) -> dict[str, Any]:
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError("Type d’événement non supporté")
    event_id = event_id or str(uuid.uuid4())
    payload = dict(payload or {})
    rules = [_row_rule(r) for r in fetch_all("SELECT * FROM action_rules WHERE workspace_id=:ws AND event_type=:event AND enabled=1 ORDER BY created_at", {"ws": workspace_id, "event": event_type})]
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    event = {"workspace_id": workspace_id, "event_type": event_type, "event_id": event_id, "dataset_id": dataset_id, "payload": payload}
    for rule in rules:
        if not _rule_matches(rule, payload, dataset_id):
            continue
        fp = _fingerprint(rule["id"], event_type, event_id, payload)
        duplicate = fetch_one("SELECT id,created_at,status FROM action_runs WHERE workspace_id=:ws AND rule_id=:rule AND fingerprint=:fp ORDER BY created_at DESC LIMIT 1", {"ws": workspace_id, "rule": rule["id"], "fp": fp})
        if duplicate and _within_window(duplicate.get("created_at"), int(rule.get("dedupe_minutes") or 0)):
            skipped.append({"rule_id": rule["id"], "reason": "dedupe", "existing_run_id": duplicate["id"]})
            continue
        last = fetch_one("SELECT id,created_at FROM action_runs WHERE workspace_id=:ws AND rule_id=:rule AND status NOT IN ('suppressed_dedupe','suppressed_throttle') ORDER BY created_at DESC LIMIT 1", {"ws": workspace_id, "rule": rule["id"]})
        approval = _approval_required(rule, payload)
        status = "pending_approval" if approval else "queued"
        scheduled_for = None
        if last and int(rule.get("throttle_minutes") or 0) > 0 and _within_window(last.get("created_at"), int(rule["throttle_minutes"])):
            status = "suppressed_throttle"
        elif status != "pending_approval":
            scheduled_for = _quiet_until(rule.get("quiet_hours"))
            if scheduled_for:
                status = "scheduled"
        run_id = str(uuid.uuid4())
        now = utcnow()
        rendered = _render_payload(rule, event)
        execute("""INSERT INTO action_runs(id,workspace_id,rule_id,destination_id,event_type,event_id,dataset_id,status,fingerprint,trigger_payload_json,rendered_payload_json,
                   approval_required,requested_by,scheduled_for,attempt_count,created_at,updated_at)
                   VALUES(:id,:ws,:rule,:dest,:event,:eventid,:dataset,:status,:fp,:trigger,:rendered,:approval,:user,:scheduled,0,:now,:now)""",
                {"id": run_id, "ws": workspace_id, "rule": rule["id"], "dest": rule["destination_id"], "event": event_type, "eventid": event_id,
                 "dataset": dataset_id, "status": status, "fp": fp, "trigger": json_dumps(payload), "rendered": json_dumps(rendered),
                 "approval": 1 if approval else 0, "user": actor_id, "scheduled": scheduled_for, "now": now})
        if status == "pending_approval" and rule.get("approval_chain"):
            _create_run_approval_steps(run_id, workspace_id, rule)
        execute("UPDATE action_rules SET last_triggered_at=:now WHERE id=:id", {"now": now, "id": rule["id"]})
        run = get_run(workspace_id, run_id)
        created.append(run)
        if enqueue and status == "queued":
            _enqueue_run(run, rule)
    return {"event_id": event_id, "event_type": event_type, "matched_rules": len(created) + len(skipped), "runs": created, "skipped": skipped}


def _approval_steps(run_id: str) -> list[dict[str, Any]]:
    return fetch_all("SELECT * FROM action_approval_steps WHERE run_id=:run ORDER BY step_order", {"run": run_id})


def get_run(workspace_id: str, run_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT * FROM action_runs WHERE id=:id AND workspace_id=:ws", {"id": run_id, "ws": workspace_id})
    if not row:
        raise KeyError("Exécution d'action introuvable")
    item = _row_run(row)
    item["attempts"] = fetch_all("SELECT * FROM action_delivery_attempts WHERE run_id=:run ORDER BY attempt_number", {"run": run_id})
    item["approval_steps"] = _approval_steps(run_id)
    return item


def _current_pending_step(run: dict[str, Any]) -> dict[str, Any] | None:
    return next((s for s in run.get("approval_steps") or [] if s.get("status") == "pending"), None)


def _assert_step_actor(actor_id: str, workspace_id: str, step: dict[str, Any]) -> None:
    if step.get("required_user_id") and str(step["required_user_id"]) != str(actor_id):
        raise PermissionError("Cette étape est assignée à un autre approbateur")
    if step.get("required_role"):
        role_row = fetch_one("SELECT role FROM workspace_members WHERE workspace_id=:ws AND user_id=:user", {"ws": workspace_id, "user": actor_id})
        if not role_row or role_row.get("role") != step.get("required_role"):
            raise PermissionError(f"Cette étape exige le rôle {step.get('required_role')}")


def approve_run(actor_id: str, workspace_id: str, run_id: str, note: str = "") -> dict[str, Any]:
    run = get_run(workspace_id, run_id)
    if run["status"] != "pending_approval":
        raise ValueError("Cette action n'est pas en attente d'approbation")
    rule = get_rule(workspace_id, run["rule_id"])
    step = _current_pending_step(run)
    now = utcnow()
    if step:
        _assert_step_actor(actor_id, workspace_id, step)
        execute("UPDATE action_approval_steps SET status='approved',acted_by=:user,note=:note,acted_at=:at WHERE id=:id AND status='pending'",
                {"user": actor_id, "note": note.strip(), "at": now, "id": step["id"]})
        remaining = fetch_one("SELECT COUNT(*) AS n FROM action_approval_steps WHERE run_id=:run AND status='pending'", {"run": run_id}) or {"n": 0}
        if int(remaining.get("n") or 0) > 0:
            execute("UPDATE action_runs SET approval_note=:note,updated_at=:at WHERE id=:id", {"note": note.strip(), "at": now, "id": run_id})
            return get_run(workspace_id, run_id)
    scheduled = _quiet_until(rule.get("quiet_hours"))
    status = "scheduled" if scheduled else "approved"
    execute("UPDATE action_runs SET status=:status,approved_by=:user,approval_note=:note,approved_at=:at,scheduled_for=:scheduled,updated_at=:at WHERE id=:id AND workspace_id=:ws",
            {"status": status, "user": actor_id, "note": note.strip(), "at": now, "scheduled": scheduled, "id": run_id, "ws": workspace_id})
    updated = get_run(workspace_id, run_id)
    if status == "approved":
        _enqueue_run(updated, rule)
        updated = get_run(workspace_id, run_id)
    return updated


def reject_run(actor_id: str, workspace_id: str, run_id: str, note: str = "") -> dict[str, Any]:
    run = get_run(workspace_id, run_id)
    if run["status"] != "pending_approval":
        raise ValueError("Cette action n'est pas en attente d'approbation")
    step = _current_pending_step(run)
    now = utcnow()
    if step:
        _assert_step_actor(actor_id, workspace_id, step)
        execute("UPDATE action_approval_steps SET status='rejected',acted_by=:user,note=:note,acted_at=:at WHERE id=:id AND status='pending'",
                {"user": actor_id, "note": note.strip(), "at": now, "id": step["id"]})
        execute("UPDATE action_approval_steps SET status='skipped' WHERE run_id=:run AND status='pending'", {"run": run_id})
    execute("UPDATE action_runs SET status='rejected',approved_by=:user,approval_note=:note,approved_at=:at,finished_at=:at,updated_at=:at WHERE id=:id AND workspace_id=:ws",
            {"user": actor_id, "note": note.strip(), "at": now, "id": run_id, "ws": workspace_id})
    return get_run(workspace_id, run_id)


def replay_run(actor_id: str, workspace_id: str, run_id: str) -> dict[str, Any]:
    original = get_run(workspace_id, run_id)
    rule = get_rule(workspace_id, original["rule_id"])
    new_id = str(uuid.uuid4())
    now = utcnow()
    approval = _approval_required(rule, original.get("trigger_payload") or {})
    scheduled = None if approval else _quiet_until(rule.get("quiet_hours"))
    status = "pending_approval" if approval else ("scheduled" if scheduled else "approved")
    execute("""INSERT INTO action_runs(id,workspace_id,rule_id,destination_id,event_type,event_id,dataset_id,status,fingerprint,trigger_payload_json,rendered_payload_json,
               approval_required,requested_by,scheduled_for,attempt_count,replay_of,created_at,updated_at)
               VALUES(:id,:ws,:rule,:dest,:event,:eventid,:dataset,:status,:fp,:trigger,:rendered,:approval,:user,:scheduled,0,:replay,:now,:now)""",
            {"id": new_id, "ws": workspace_id, "rule": original["rule_id"], "dest": original["destination_id"], "event": original["event_type"],
             "eventid": f"replay:{original['event_id']}:{new_id}", "dataset": original.get("dataset_id"), "status": status,
             "fp": hashlib.sha256(f"replay:{original['fingerprint']}:{new_id}".encode()).hexdigest(), "trigger": json_dumps(original.get("trigger_payload") or {}),
             "rendered": json_dumps(original.get("rendered_payload") or {}), "approval": 1 if approval else 0, "user": actor_id,
             "scheduled": scheduled, "replay": run_id, "now": now})
    if approval and rule.get("approval_chain"):
        _create_run_approval_steps(new_id, workspace_id, rule)
    run = get_run(workspace_id, new_id)
    if status == "approved":
        _enqueue_run(run, rule)
        run = get_run(workspace_id, new_id)
    return run


def _fetch_oauth_token(destination: dict[str, Any]) -> str:
    oauth = destination.get("oauth") or {}
    credential = destination.get("credential") or {}
    token_url = str(oauth.get("token_url") or "")
    _validate_webhook_url(token_url, resolve_dns=True)
    data = {"grant_type": "client_credentials"}
    if oauth.get("scope"):
        data["scope"] = str(oauth["scope"])
    if oauth.get("audience"):
        data["audience"] = str(oauth["audience"])
    auth = _b64mod.b64encode(f"{credential.get('client_id','')}:{credential.get('client_secret','')}".encode()).decode()
    req = Request(token_url, data=_urlencode(data).encode(), headers={"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Basic {auth}"}, method="POST")
    try:
        with urlopen(req, timeout=10.0) as response:
            payload = json.loads(response.read(65536).decode("utf-8", errors="replace"))
    except HTTPError as exc:
        raise RuntimeError(f"OAuth2 token endpoint HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"OAuth2 token endpoint inaccessible: {exc.reason}") from exc
    token = str(payload.get("access_token") or "")
    if not token:
        raise RuntimeError("OAuth2: access_token absent de la réponse")
    return token


def _auth_headers(destination: dict[str, Any]) -> dict[str, str]:
    ctype = destination.get("credential_type") or "none"
    cred = destination.get("credential") or {}
    if ctype == "bearer":
        return {"Authorization": f"Bearer {cred.get('token','')}"}
    if ctype == "basic":
        secret = cred.get("api_token") or cred.get("password") or ""
        value = _b64mod.b64encode(f"{cred.get('username','')}:{secret}".encode()).decode()
        return {"Authorization": f"Basic {value}"}
    if ctype == "oauth2_client_credentials":
        return {"Authorization": f"Bearer {_fetch_oauth_token(destination)}"}
    return {}


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None, timeout: float = 10.0) -> tuple[int, str]:
    _validate_webhook_url(url, resolve_dns=True)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    req = Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "DataVision-Actions/2.11", **(headers or {})}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as response:
            return int(response.status), response.read(8192).decode("utf-8", errors="replace")
    except HTTPError as exc:
        raw = exc.read(8192).decode("utf-8", errors="replace") if getattr(exc, "fp", None) else str(exc)
        return int(exc.code), raw
    except URLError as exc:
        raise RuntimeError(f"Destination inaccessible: {exc.reason}") from exc


def _message_from_payload(payload: dict[str, Any]) -> str:
    return str(payload.get("message") or payload.get("text") or payload.get("title") or json.dumps(payload, ensure_ascii=False, default=str))


def _deliver_email(destination: dict[str, Any], payload: dict[str, Any]) -> tuple[int, str]:
    config = destination.get("config") or {}
    credential = destination.get("credential") or {}
    host = str(config.get("smtp_host") or "")
    port = int(config.get("smtp_port") or (465 if config.get("ssl") else 587))
    recipients = payload.get("to") or config.get("to") or []
    if isinstance(recipients, str):
        recipients = [x.strip() for x in recipients.split(",") if x.strip()]
    if not recipients:
        raise ValueError("Aucun destinataire email configuré")
    msg = _EmailMessage()
    msg["Subject"] = str(payload.get("subject") or config.get("subject") or "DataVision notification")
    msg["From"] = str(config.get("from_email"))
    msg["To"] = ", ".join(str(x) for x in recipients)
    msg.set_content(_message_from_payload(payload))
    if payload.get("html"):
        msg.add_alternative(str(payload["html"]), subtype="html")
    smtp_cls = _smtplib.SMTP_SSL if config.get("ssl") else _smtplib.SMTP
    with smtp_cls(host, port, timeout=10) as smtp:
        if not config.get("ssl") and config.get("starttls", True):
            smtp.starttls()
        if destination.get("credential_type") == "smtp":
            smtp.login(str(credential.get("username") or ""), str(credential.get("password") or ""))
        elif destination.get("credential_type") == "oauth2_client_credentials":
            token = _fetch_oauth_token(destination)
            user = str(credential.get("username") or config.get("from_email") or "")
            auth_string = f"user={user}\x01auth=Bearer {token}\x01\x01"
            code, resp = smtp.docmd("AUTH", "XOAUTH2 " + _b64mod.b64encode(auth_string.encode()).decode())
            if int(code) >= 400:
                raise RuntimeError(f"SMTP OAuth2 refusé: {code} {resp!r}")
        smtp.send_message(msg)
    return 250, f"email accepted for {len(recipients)} recipient(s)"


def _deliver_destination(destination: dict[str, Any], run: dict[str, Any]) -> tuple[int, str]:
    kind = destination.get("kind") or "webhook"
    payload = dict(run.get("rendered_payload") or {})
    auth_headers = _auth_headers(destination)
    if kind == "webhook":
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode()
        ts = str(int(time.time()))
        secret = str(destination.get("secret") or "")
        signature = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest() if secret else ""
        headers = {"Content-Type": "application/json", "User-Agent": "DataVision-Actions/2.11", "X-DataVision-Timestamp": ts,
                   "X-DataVision-Run-ID": run["id"], "Idempotency-Key": run["fingerprint"], **auth_headers}
        if signature:
            headers["X-DataVision-Signature"] = f"v1={signature}"
        for k, v in (destination.get("headers") or {}).items():
            if str(k).lower() not in {"host", "content-length", "x-datavision-signature", "x-datavision-timestamp", "idempotency-key"}:
                headers[str(k)] = str(v)
        return _post_webhook(destination, body, headers)
    if kind == "slack":
        config = destination.get("config") or {}
        if config.get("mode") == "api":
            out: dict[str, Any] = {"channel": config.get("channel"), "text": _message_from_payload(payload)}
            if payload.get("blocks"):
                out["blocks"] = payload["blocks"]
            code, raw = _post_json(destination["webhook_url"], out, auth_headers)
            if 200 <= code < 300:
                try:
                    parsed = json.loads(raw or "{}")
                    if parsed.get("ok") is False:
                        return 422, str(parsed.get("error") or "Slack API error")
                except Exception:
                    pass
            return code, raw
        return _post_json(destination["webhook_url"], {"text": _message_from_payload(payload), **({"blocks": payload["blocks"]} if payload.get("blocks") else {})}, auth_headers)
    if kind == "teams":
        out = payload if payload.get("attachments") else {"text": _message_from_payload(payload)}
        return _post_json(destination["webhook_url"], out, auth_headers)
    if kind == "jira":
        config = destination.get("config") or {}
        summary = str(payload.get("summary") or payload.get("title") or _message_from_payload(payload))[:240]
        description = str(payload.get("description") or payload.get("message") or "DataVision governed action")
        fields: dict[str, Any] = {
            "project": {"key": config.get("project_key")},
            "summary": summary,
            "issuetype": {"name": config.get("issue_type") or "Task"},
            "description": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": description[:30000]}]}]},
        }
        if config.get("labels"):
            fields["labels"] = list(config.get("labels"))
        return _post_json(destination["webhook_url"].rstrip("/") + "/rest/api/3/issue", {"fields": fields}, {**auth_headers, "Accept": "application/json"})
    if kind == "email":
        return _deliver_email(destination, payload)
    raise RuntimeError(f"Destination native inconnue: {kind}")


def test_destination_delivery(workspace_id: str, destination_id: str, actor_id: str) -> dict[str, Any]:
    destination = _get_destination_secret(workspace_id, destination_id)
    synthetic = {
        "id": f"test-{uuid.uuid4()}",
        "fingerprint": hashlib.sha256(f"test:{destination_id}:{time.time_ns()}".encode()).hexdigest(),
        "rendered_payload": {"message": "Test DataVision — destination opérationnelle", "title": "DataVision connector test", "subject": "DataVision connector test"},
    }
    code, response = _deliver_destination(destination, synthetic)
    return {"ok": 200 <= int(code) < 300, "response_code": int(code), "response": str(response)[:2000], "kind": destination.get("kind"), "tested_by": actor_id}


def execute_action_run(run_id: str) -> dict[str, Any]:
    row = fetch_one("SELECT workspace_id FROM action_runs WHERE id=:id", {"id": run_id})
    if not row:
        raise KeyError("Exécution d'action introuvable")
    ws = row["workspace_id"]
    run = get_run(ws, run_id)
    if run["status"] in {"completed", "rejected", "cancelled"}:
        return run
    if run["status"] == "pending_approval":
        raise PermissionError("Approbation humaine requise avant exécution")
    if run["status"] == "scheduled":
        due = _parse_iso(run.get("scheduled_for"))
        if due and due > datetime.now(timezone.utc):
            raise RuntimeError("Action planifiée pour une exécution ultérieure")
    destination = _get_destination_secret(ws, run["destination_id"])
    if not destination.get("enabled"):
        raise RuntimeError("Destination désactivée")
    count = fetch_one("SELECT COUNT(*) AS n FROM action_delivery_attempts WHERE run_id=:run", {"run": run_id}) or {"n": 0}
    attempt = int(count.get("n") or 0) + 1
    attempt_id = str(uuid.uuid4())
    started = utcnow()
    perf = time.perf_counter()
    execute("INSERT INTO action_delivery_attempts(id,run_id,workspace_id,attempt_number,status,created_at) VALUES(:id,:run,:ws,:n,'running',:at)",
            {"id": attempt_id, "run": run_id, "ws": ws, "n": attempt, "at": started})
    execute("UPDATE action_runs SET status='running',started_at=COALESCE(started_at,:at),attempt_count=:n,updated_at=:at WHERE id=:id", {"at": started, "n": attempt, "id": run_id})
    try:
        code, response = _deliver_destination(destination, run)
        latency = (time.perf_counter() - perf) * 1000
        ok = 200 <= int(code) < 300
        finished = utcnow()
        execute("UPDATE action_delivery_attempts SET status=:status,response_code=:code,response_body=:body,latency_ms=:latency,finished_at=:at WHERE id=:id",
                {"status": "completed" if ok else "failed", "code": code, "body": str(response)[:8000], "latency": latency, "at": finished, "id": attempt_id})
        if not ok:
            execute("UPDATE action_runs SET status='failed',last_response_code=:code,last_response_body=:body,error=:error,updated_at=:at WHERE id=:id",
                    {"code": code, "body": str(response)[:8000], "error": f"{destination.get('kind')} delivery HTTP/status {code}", "at": finished, "id": run_id})
            raise RuntimeError(f"Destination {destination.get('kind')} status {code}")
        execute("UPDATE action_runs SET status='completed',last_response_code=:code,last_response_body=:body,error=NULL,finished_at=:at,updated_at=:at WHERE id=:id",
                {"code": code, "body": str(response)[:8000], "at": finished, "id": run_id})
    except Exception as exc:
        latency = (time.perf_counter() - perf) * 1000
        finished = utcnow()
        execute("UPDATE action_delivery_attempts SET status='failed',error=:error,latency_ms=:latency,finished_at=:at WHERE id=:id",
                {"error": str(exc)[:8000], "latency": latency, "at": finished, "id": attempt_id})
        execute("UPDATE action_runs SET status='failed',error=:error,updated_at=:at WHERE id=:id", {"error": str(exc)[:8000], "at": finished, "id": run_id})
        raise
    return get_run(ws, run_id)


def action_summary(workspace_id: str) -> dict[str, Any]:
    counts = fetch_all("SELECT status,COUNT(*) AS n FROM action_runs WHERE workspace_id=:ws GROUP BY status", {"ws": workspace_id})
    status_counts = {str(x["status"]): int(x["n"]) for x in counts}
    completed = status_counts.get("completed", 0)
    failed = status_counts.get("failed", 0)
    rules = list_rules(workspace_id)
    destinations = list_destinations(workspace_id)
    kinds: dict[str, int] = {}
    for d in destinations:
        kinds[str(d.get("kind") or "webhook")] = kinds.get(str(d.get("kind") or "webhook"), 0) + 1
    staged = int((fetch_one("SELECT COUNT(*) AS n FROM action_rules r JOIN action_rule_approval_chains c ON c.rule_id=r.id WHERE r.workspace_id=:ws", {"ws": workspace_id}) or {"n": 0})["n"])
    return {"destinations": len(destinations), "destination_kinds": kinds, "rules": len(rules), "active_rules": sum(1 for r in rules if r.get("enabled")),
            "staged_approval_rules": staged, "runs": sum(status_counts.values()), "completed": completed, "failed": failed,
            "pending_approval": status_counts.get("pending_approval", 0), "scheduled": status_counts.get("scheduled", 0),
            "delivery_success_pct": round(100.0 * completed / max(completed + failed, 1), 2) if completed + failed else None,
            "status_counts": status_counts,
            "security": {"signed_webhooks": True, "ssrf_guard": True, "idempotency_keys": True, "human_approval": True,
                         "staged_approvals": True, "encrypted_credentials": True, "oauth2_client_credentials": True},
            "native_connectors": ["slack", "teams", "jira", "email", "webhook"]}

# v2.11 list view includes approval progress without forcing the frontend to
# fetch every run individually.
def list_runs(workspace_id: str, status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    params = {"ws": workspace_id, "limit": max(1, min(int(limit), 500))}
    where = "workspace_id=:ws"
    if status and status != "all":
        where += " AND status=:status"
        params["status"] = status
    rows = fetch_all(f"SELECT * FROM action_runs WHERE {where} ORDER BY created_at DESC LIMIT :limit", params)
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _row_run(row)
        item["approval_steps"] = _approval_steps(str(item["id"]))
        out.append(item)
    return out
