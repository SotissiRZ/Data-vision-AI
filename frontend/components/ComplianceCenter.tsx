
'use client';

import { useEffect, useMemo, useState } from 'react';
import { getCdcCompliance, getProductionAcceptance } from '../lib/api';
import styles from './ComplianceCenter.module.css';

type AnyObj = Record<string, any>;

export function ComplianceCenter({ setError }: { setError: (message: string) => void }) {
  const [report, setReport] = useState<AnyObj | null>(null);
  const [acceptance, setAcceptance] = useState<AnyObj | null>(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState('');

  async function load() {
    setBusy(true); setError(''); setLoadError('');
    try {
      const [matrix, production] = await Promise.all([
        getCdcCompliance(),
        getProductionAcceptance(),
      ]);
      setReport(matrix);
      setAcceptance(production);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setLoadError(message); setError(message);
    } finally { setBusy(false); }
  }

  useEffect(() => { void load(); }, []);

  const rows = useMemo(() => {
    const all = report?.requirements ?? [];
    const needle = query.trim().toLowerCase();
    return all.filter((row: AnyObj) => {
      if (statusFilter !== 'all' && row.status !== statusFilter) return false;
      if (priorityFilter !== 'all' && row.priority !== priorityFilter) return false;
      if (!needle) return true;
      return `${row.section} ${row.title} ${(row.gaps ?? []).join(' ')}`.toLowerCase().includes(needle);
    });
  }, [report, statusFilter, priorityFilter, query]);

  if (!report) return <div className={styles.loading}>{busy ? 'Audit CDC en cours…' : <div><b>Matrice CDC indisponible.</b>{loadError&&<p>{loadError}</p>}<button onClick={()=>void load()}>↻ Réessayer</button></div>}</div>;
  const summary = report.summary;
  const signoffRequired = acceptance?.signoff_required ?? [];

  return <div className={styles.page}>
    <div className={styles.title}>
      <div>
        <span>CDC COMPLIANCE · EVIDENCE · ACCEPTANCE</span>
        <h1>CDC & Production Acceptance</h1>
        <p>Matrice auditable du cahier des charges : chaque statut est relié à des preuves dans le dépôt et aux gaps encore ouverts.</p>
      </div>
      <button onClick={() => void load()} disabled={busy}>{busy ? 'Audit…' : '↻ Réévaluer'}</button>
    </div>

    <div className={styles.scoreGrid}>
      <article className={styles.coverage}><span>Couverture pondérée</span><b>{summary.weighted_coverage_percent}%</b><small>{summary.implemented} implémentés · {summary.partial} partiels · {summary.missing} manquants</small></article>
      <article><span>MVP obligatoire</span><b className={styles.good}>{summary.mvp_acceptance}</b><small>{summary.mvp_items?.filter((x:AnyObj)=>x.pass).length ?? 0}/{summary.mvp_items?.length ?? 0} contrôles présents</small></article>
      <article><span>Preuves</span><b className={summary.evidence_complete ? styles.good : styles.bad}>{summary.evidence_complete ? 'complètes' : 'incomplètes'}</b><small>{report.missing_evidence?.length ?? 0} référence(s) absente(s)</small></article>
      <article><span>Acceptation globale</span><b className={summary.overall_acceptance === 'accepted' ? styles.good : styles.warn}>{summary.overall_acceptance}</b><small>La conformité CDC 100% n’est pas déclarée tant que des sections restent partielles.</small></article>
    </div>

    <section className={styles.panel}>
      <header><h3>Gates de production</h3><span>{acceptance?.product_version ?? report.product_version}</span></header>
      <div className={styles.gates}>
        {(acceptance?.gates ?? []).map((gate:AnyObj)=><div key={gate.id}><span className={`${styles.status} ${styles[gate.status]}`}>{gate.status}</span><b>{gate.label}</b><small>{gate.blocking ? 'bloquant pour une signature complète' : 'non bloquant'}</small></div>)}
      </div>
      {signoffRequired.length>0&&<div className={styles.signoff}><b>Sign-off encore requis</b>{signoffRequired.map((item:string)=><span key={item}>• {item}</span>)}</div>}
    </section>

    <section className={styles.panel}>
      <header><h3>Gaps prioritaires</h3><span>P0 / P1</span></header>
      <div className={styles.gapGrid}>
        {['P0','P1'].map(priority=><div key={priority}><b>{priority}</b>{(report.priority_gaps?.[priority] ?? []).length ? (report.priority_gaps[priority] ?? []).map((gap:AnyObj)=><article key={gap.section}><span>§{gap.section}</span><div><strong>{gap.title}</strong><p>{(gap.gaps ?? []).join(' ') || 'Couverture partielle.'}</p></div></article>) : <small>Aucun gap.</small>}</div>)}
      </div>
    </section>

    <section className={styles.panel}>
      <header><h3>Matrice des 75 sections</h3><span>{rows.length} affichées</span></header>
      <div className={styles.filters}>
        <input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Rechercher une section, un gap…"/>
        <select value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}><option value="all">Tous statuts</option><option value="implemented">Implémenté</option><option value="partial">Partiel</option><option value="missing">Manquant</option></select>
        <select value={priorityFilter} onChange={e=>setPriorityFilter(e.target.value)}><option value="all">Toutes priorités</option><option value="P0">P0</option><option value="P1">P1</option><option value="P2">P2</option></select>
      </div>
      <div className={styles.tableWrap}><table><thead><tr><th>§</th><th>Exigence</th><th>Statut</th><th>Priorité</th><th>Preuves</th><th>Gap</th></tr></thead><tbody>{rows.map((row:AnyObj)=><tr key={row.section}><td>{row.section}</td><td><b>{row.title}</b></td><td><span className={`${styles.status} ${styles[row.status]}`}>{row.status}</span></td><td><span className={`${styles.priority} ${styles[row.priority]}`}>{row.priority}</span></td><td><div className={styles.evidence}>{[...(row.evidence??[]),...(row.tests??[])].map((item:AnyObj)=><code key={item.path} className={item.exists?styles.exists:styles.missing}>{item.exists?'✓':'×'} {item.path}</code>)}</div></td><td>{(row.gaps??[]).join(' ') || '—'}</td></tr>)}</tbody></table></div>
    </section>

    <div className={styles.method}><b>Méthodologie</b><span>implemented = 1 point · partial = 0,5 · missing = 0. Le score mesure la couverture du CDC, pas une certification externe ni la qualité scientifique d’un résultat particulier.</span></div>
  </div>;
}
