'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  captureRegulatoryPosture, createRegulatoryEvidencePack, createRegulatoryException,
  decideRegulatoryException, downloadRegulatoryEvidencePack, getRegulatoryCatalog,
  getRegulatoryEvidencePacks, getRegulatoryExceptions, getRegulatoryHistory,
  getRegulatoryPosture, getRegulatoryRemediation,
} from '../lib/api';
import styles from './RegulatoryCompliancePanel.module.css';

type AnyObj = Record<string, any>;

export function RegulatoryCompliancePanel({token,workspaceId,setError}:{token:string;workspaceId:string;setError:(message:string)=>void}){
  const [framework,setFramework]=useState('');
  const [catalog,setCatalog]=useState<AnyObj|null>(null);
  const [posture,setPosture]=useState<AnyObj|null>(null);
  const [history,setHistory]=useState<AnyObj[]>([]);
  const [exceptions,setExceptions]=useState<AnyObj[]>([]);
  const [remediation,setRemediation]=useState<AnyObj|null>(null);
  const [exports,setExports]=useState<AnyObj[]>([]);
  const [busy,setBusy]=useState(false);
  const [controlId,setControlId]=useState('');
  const [reason,setReason]=useState('');
  const [owner,setOwner]=useState('');
  const [expiresAt,setExpiresAt]=useState('');

  async function load(nextFramework=framework){
    if(!token||!workspaceId)return;
    setBusy(true); setError('');
    try{
      const [c,p,h,e,r,x]=await Promise.all([
        getRegulatoryCatalog(token,workspaceId,nextFramework||undefined),
        getRegulatoryPosture(token,workspaceId,nextFramework||undefined),
        getRegulatoryHistory(token,workspaceId,nextFramework||undefined),
        getRegulatoryExceptions(token,workspaceId),
        getRegulatoryRemediation(token,workspaceId,nextFramework||undefined),
        getRegulatoryEvidencePacks(token,workspaceId),
      ]);
      setCatalog(c);setPosture(p);setHistory(h.history??[]);setExceptions(e.exceptions??[]);setRemediation(r);setExports(x.exports??[]);
      if(!controlId&&c.controls?.[0]?.id)setControlId(c.controls[0].id);
    }catch(error:unknown){setError(error instanceof Error?error.message:String(error));}
    finally{setBusy(false);}
  }
  useEffect(()=>{void load();},[token,workspaceId]);
  useEffect(()=>{if(token&&workspaceId)void load(framework);},[framework]);

  const summary=posture?.summary??{};
  const activeExceptions=useMemo(()=>exceptions.filter(x=>x.active),[exceptions]);
  const latestHistory=history.slice(0,8).reverse();

  async function snapshot(){setBusy(true);try{await captureRegulatoryPosture(token,workspaceId,framework||undefined);await load();}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  async function evidence(){setBusy(true);try{await createRegulatoryEvidencePack(token,workspaceId,framework||undefined);await load();}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  async function requestException(){
    if(!controlId||!reason.trim()||!expiresAt)return;
    setBusy(true);
    try{
      await createRegulatoryException(token,workspaceId,{control_id:controlId,reason:reason.trim(),expires_at:new Date(expiresAt).toISOString(),owner});
      setReason('');setOwner('');setExpiresAt('');await load();
    }catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  async function decide(id:string,decision:'approved'|'rejected'|'revoked'){
    setBusy(true);try{await decideRegulatoryException(token,workspaceId,id,decision);await load();}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  }
  async function download(item:AnyObj){
    try{
      const blob=await downloadRegulatoryEvidencePack(token,workspaceId,item.id);
      const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download=`datavision-regulatory-evidence-${item.id}.zip`; a.click(); URL.revokeObjectURL(url);
    }catch(e:unknown){setError(e instanceof Error?e.message:String(e));}
  }

  return <section className={styles.panel}>
    <div className={styles.head}>
      <div><span>CONFORMITÉ RÉGLEMENTAIRE · v2.65</span><h3>Posture, exceptions & preuves</h3><p>Mapping de familles de contrôles, historique et evidence packs. Aucun statut affiché ne constitue une certification externe.</p></div>
      <div className={styles.actions}><select value={framework} onChange={e=>setFramework(e.target.value)} disabled={busy}><option value="">Tous les référentiels</option>{(catalog?.frameworks??[]).map((f:AnyObj)=><option key={f.id} value={f.id}>{f.name} · {f.version}</option>)}</select><button onClick={()=>void snapshot()} disabled={busy}>Capturer</button><button onClick={()=>void evidence()} disabled={busy}>Exporter les preuves</button></div>
    </div>

    <div className={styles.scoreGrid}>
      <article><span>Conformité stricte</span><b>{summary.compliant_percent??0}%</b><small>{summary.pass??0}/{summary.control_count??0} contrôles en pass</small></article>
      <article><span>Posture gérée</span><b>{summary.managed_percent??0}%</b><small>Inclut {summary.excepted??0} exception(s) approuvée(s)</small></article>
      <article><span>Dérives</span><b>{summary.fail??0}</b><small>{summary.unknown??0} état(s) inconnu(s)</small></article>
      <article><span>Exceptions actives</span><b>{activeExceptions.length}</b><small>Une exception n'est jamais comptée comme conformité stricte</small></article>
    </div>

    <div className={styles.twoCol}>
      <div className={styles.card}><div className={styles.cardHead}><h4>Contrôles effectifs</h4><span>{posture?.controls?.length??0}</span></div><div className={styles.controlList}>{(posture?.controls??[]).map((c:AnyObj)=><div key={c.id} className={styles.control}><span className={`${styles.dot} ${styles[c.effective_status]||''}`}/><div><b>{c.id} · {c.name}</b><small>{c.category} · source {c.source_control}</small>{c.exception&&<em>Exception jusqu'au {new Date(c.exception.expires_at).toLocaleDateString('fr-FR')}</em>}</div><strong>{c.effective_status}</strong></div>)}</div></div>
      <div className={styles.card}><div className={styles.cardHead}><h4>Historique de posture</h4><span>{history.length} snapshot(s)</span></div><div className={styles.history}>{latestHistory.length?latestHistory.map((x:AnyObj)=><div key={x.id}><time>{x.created_at?new Date(x.created_at).toLocaleDateString('fr-FR'):''}</time><div><i style={{width:`${Math.max(0,Math.min(100,Number(x.score)||0))}%`}}/></div><b>{Number(x.score??0).toFixed(1)}%</b></div>):<p>Aucun snapshot historique.</p>}</div><div className={styles.digest}>SHA-256 actuel : <code>{String(posture?.sha256??'—').slice(0,24)}</code></div></div>
    </div>

    <div className={styles.twoCol}>
      <div className={styles.card}><div className={styles.cardHead}><h4>Exceptions gouvernées</h4><span>demande → approbation → expiration</span></div><div className={styles.exceptionForm}><select value={controlId} onChange={e=>setControlId(e.target.value)}>{(catalog?.controls??[]).map((c:AnyObj)=><option key={c.id} value={c.id}>{c.id} · {c.name}</option>)}</select><input value={owner} onChange={e=>setOwner(e.target.value)} placeholder="Owner / responsable"/><input type="datetime-local" value={expiresAt} onChange={e=>setExpiresAt(e.target.value)}/><textarea value={reason} onChange={e=>setReason(e.target.value)} placeholder="Justification et contrôles compensatoires…"/><button onClick={()=>void requestException()} disabled={busy||reason.trim().length<10||!expiresAt}>Soumettre l'exception</button></div><div className={styles.exceptionList}>{exceptions.slice(0,8).map((x:AnyObj)=><article key={x.id}><div><b>{x.control_id}</b><span className={styles[x.status]||''}>{x.status}{x.expired?' · expirée':''}</span></div><p>{x.reason}</p><small>{x.owner||'Sans owner'} · expiration {x.expires_at?new Date(x.expires_at).toLocaleString('fr-FR'):'—'}</small>{x.status==='pending'&&<div><button onClick={()=>void decide(x.id,'approved')} disabled={busy}>Approuver</button><button onClick={()=>void decide(x.id,'rejected')} disabled={busy}>Rejeter</button></div>}{x.active&&<button onClick={()=>void decide(x.id,'revoked')} disabled={busy}>Révoquer</button>}</article>)}{!exceptions.length&&<p>Aucune exception.</p>}</div></div>
      <div className={styles.card}><div className={styles.cardHead}><h4>Remédiation assistée</h4><span>propositions uniquement</span></div><div className={styles.remediation}>{(remediation?.actions??[]).map((a:AnyObj)=><article key={a.control_id}><span className={`${styles.priority} ${styles[a.priority]}`}>{a.priority}</span><div><b>{a.control_id} · {a.control_name}</b><p>{a.action}</p><small>Vérification : {a.verification}</small></div></article>)}{!(remediation?.actions??[]).length&&<p>Aucune remédiation ouverte sur le référentiel sélectionné.</p>}</div></div>
    </div>

    <div className={styles.card}><div className={styles.cardHead}><h4>Evidence packs exportables</h4><span>ZIP · manifest · JSON · CSV · SHA-256</span></div><div className={styles.exports}>{exports.slice(0,6).map((x:AnyObj)=><div key={x.id}><div><b>{x.framework_id}</b><small>{x.created_at?new Date(x.created_at).toLocaleString('fr-FR'):''} · {String(x.sha256??'').slice(0,16)}</small></div><span>{x.status}</span><button onClick={()=>void download(x)}>Télécharger</button></div>)}{!exports.length&&<p>Aucun pack exporté.</p>}</div></div>
  </section>;
}
