'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  checkModelRetraining,
  getDatasetCatalog,
  getModelMonitoringHistory,
  getModelMonitorSchedule,
  getModelRegistryDetail,
  getModelRegistryEntries,
  getModelRegistrySummary,
  getModelRetrainingPolicy,
  getModelRetrainingRequests,
  registerModelInRegistry,
  runModelMonitoring,
  saveModelRetrainingPolicy,
  saveModelMonitorSchedule,
  transitionModelStage,
} from '../lib/api';
import styles from './ModelRegistryView.module.css';

type AnyObj = Record<string, any>;

type Props = {
  activeModel: AnyObj | null;
  activeDataset: AnyObj | null;
  setError: (message: string) => void;
};

const STAGE_LABELS: Record<string, string> = {
  draft: 'Draft',
  staging: 'Staging',
  production: 'Production',
  retired: 'Retired',
};

function fmt(value: unknown, digits = 3) {
  if (typeof value !== 'number') return value == null ? '—' : String(value);
  if (!Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: digits }).format(value);
}

export function ModelRegistryView({ activeModel, activeDataset, setError }: Props) {
  const [summary, setSummary] = useState<AnyObj | null>(null);
  const [entries, setEntries] = useState<AnyObj[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<AnyObj | null>(null);
  const [catalog, setCatalog] = useState<AnyObj[]>([]);
  const [monitorDatasetId, setMonitorDatasetId] = useState('');
  const [monitoring, setMonitoring] = useState<AnyObj[]>([]);
  const [monitorSchedule, setMonitorSchedule] = useState<AnyObj | null>(null);
  const [policy, setPolicy] = useState<AnyObj | null>(null);
  const [requests, setRequests] = useState<AnyObj[]>([]);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');

  const selected = useMemo(
    () => entries.find(item => item.model_id === selectedId) ?? null,
    [entries, selectedId],
  );

  async function load() {
    setError('');
    try {
      const [registry, registrySummary, datasetCatalog] = await Promise.all([
        getModelRegistryEntries(),
        getModelRegistrySummary(),
        getDatasetCatalog(),
      ]);
      const rows = registry.models ?? [];
      setEntries(rows);
      setSummary(registrySummary);
      setCatalog(datasetCatalog.datasets ?? datasetCatalog ?? []);
      const preferred = selectedId || activeModel?.model_id || rows[0]?.model_id || '';
      if (preferred) setSelectedId(preferred);
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    }
  }

  async function loadDetail(modelId: string) {
    if (!modelId) {
      setDetail(null);
      return;
    }
    try {
      const [registryDetail, history, retrainingPolicy, retrainingRequests, schedule] = await Promise.all([
        getModelRegistryDetail(modelId),
        getModelMonitoringHistory(modelId, 50),
        getModelRetrainingPolicy(modelId),
        getModelRetrainingRequests(modelId),
        getModelMonitorSchedule(modelId),
      ]);
      setDetail(registryDetail);
      setMonitoring(history.runs ?? []);
      setPolicy(retrainingPolicy);
      setRequests(retrainingRequests.requests ?? []);
      setMonitorSchedule(schedule);
      const ref = registryDetail.card?.dataset?.id;
      const next = catalog.find(item => String(item.dataset_id ?? item.id) !== String(ref));
      if (!monitorDatasetId && next) setMonitorDatasetId(String(next.dataset_id ?? next.id));
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    }
  }

  useEffect(() => { void load(); }, [activeModel?.model_id, activeDataset?.id]);
  useEffect(() => { if (selectedId) void loadDetail(selectedId); }, [selectedId, catalog.length]);

  async function registerActive() {
    if (!activeModel?.model_id) return;
    setBusy('register'); setNotice(''); setError('');
    try {
      await registerModelInRegistry(activeModel.model_id, {});
      setNotice('Modèle enregistré dans le Registry en draft.');
      await load();
      setSelectedId(activeModel.model_id);
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    } finally { setBusy(''); }
  }

  async function transition(target: 'draft' | 'staging' | 'production' | 'retired') {
    if (!selectedId) return;
    setBusy(`stage:${target}`); setNotice(''); setError('');
    try {
      await transitionModelStage(selectedId, { target_stage: target });
      setNotice(`Modèle déplacé vers ${STAGE_LABELS[target]}.`);
      await load();
      await loadDetail(selectedId);
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    } finally { setBusy(''); }
  }

  async function monitor() {
    if (!selectedId || !monitorDatasetId) return;
    setBusy('monitor'); setNotice(''); setError('');
    try {
      const run = await runModelMonitoring(selectedId, { current_dataset_id: monitorDatasetId });
      setNotice(run.status === 'degraded' ? 'Dégradation détectée.' : 'Monitoring terminé : modèle sain selon la politique courante.');
      await loadDetail(selectedId);
      await load();
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    } finally { setBusy(''); }
  }

async function saveSchedule() {
  if (!selectedId || !monitorDatasetId || !monitorSchedule) return;
  setBusy('schedule'); setError(''); setNotice('');
  try {
    const saved = await saveModelMonitorSchedule(selectedId, {
      current_dataset_id: monitorDatasetId,
      enabled: Boolean(monitorSchedule.enabled),
      interval_minutes: Number(monitorSchedule.interval_minutes || 1440),
      policy: monitorSchedule.policy ?? {},
    });
    setMonitorSchedule(saved);
    setNotice(saved.enabled ? 'Monitoring périodique activé.' : 'Monitoring périodique désactivé.');
    await load();
  } catch (error: unknown) {
    setError(error instanceof Error ? error.message : String(error));
  } finally { setBusy(''); }
}

  async function savePolicy() {
    if (!selectedId || !policy) return;
    setBusy('policy'); setError(''); setNotice('');
    try {
      const next = await saveModelRetrainingPolicy(selectedId, {
        enabled: Boolean(policy.enabled),
        min_rows: Number(policy.min_rows),
        metric_degradation_threshold: Number(policy.metric_degradation_threshold),
        feature_drift_threshold: Number(policy.feature_drift_threshold),
        cooldown_hours: Number(policy.cooldown_hours),
        auto_create_request: Boolean(policy.auto_create_request),
      });
      setPolicy(next);
      setNotice('Politique de réentraînement enregistrée.');
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    } finally { setBusy(''); }
  }

  async function checkRetraining() {
    if (!selectedId) return;
    setBusy('retrain'); setError(''); setNotice('');
    try {
      const result = await checkModelRetraining(selectedId, true);
      setNotice(
        result.request_created
          ? 'Une demande de réentraînement traçable a été créée.'
          : result.retraining_recommended
            ? 'Réentraînement recommandé, mais aucune nouvelle demande n’a été créée (cooldown/politique).'
            : 'Aucun réentraînement recommandé par la politique actuelle.',
      );
      await loadDetail(selectedId);
      await load();
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    } finally { setBusy(''); }
  }

  const stage = detail?.stage ?? selected?.stage;
  const currentRun = monitoring[0] ?? detail?.latest_monitoring ?? null;
  const driftRows = currentRun?.drift?.features ?? [];
  const activeIsRegistered = activeModel?.model_id && entries.some(item => item.model_id === activeModel.model_id);

  return <div className={styles.page}>
    <div className={styles.titleRow}>
      <div>
        <span className={styles.eyebrow}>MODEL REGISTRY · LIFECYCLE · MONITORING · RETRAINING</span>
        <h1>Model Registry & MLOps</h1>
        <p>Versionnez, promouvez et surveillez les modèles sans contourner la certification, le Responsible AI Gate ou la revue humaine.</p>
      </div>
      {activeModel?.model_id && !activeIsRegistered && <button className={styles.primary} disabled={busy === 'register'} onClick={() => void registerActive()}>{busy === 'register' ? 'Enregistrement…' : 'Enregistrer le modèle actif'}</button>}
    </div>

    <div className={styles.metrics}>
      <div><span>Registry</span><b>{summary?.total_models ?? 0}</b></div>
      <div><span>Production</span><b>{summary?.by_stage?.production ?? 0}</b></div>
      <div><span>Staging</span><b>{summary?.by_stage?.staging ?? 0}</b></div>
      <div><span>Runs dégradés</span><b>{summary?.degraded_monitoring_runs ?? 0}</b></div>
      <div><span>Retraining en attente</span><b>{summary?.pending_retraining_requests ?? 0}</b></div>
      <div><span>Monitoring planifié</span><b>{summary?.active_monitor_schedules ?? 0}</b></div>
    </div>

    {notice && <div className={styles.notice}>{notice}</div>}

    <div className={styles.layout}>
      <section className={styles.panel}>
        <header><h3>Versions enregistrées</h3><span>{entries.length} modèle(s)</span></header>
        <div className={styles.registryList}>
          {entries.map(item => <button key={item.model_id} className={selectedId === item.model_id ? styles.selected : ''} onClick={() => setSelectedId(item.model_id)}>
            <div><b>{item.name}</b><small>v{item.version_no} · {item.card?.algorithm} · {item.card?.target}</small></div>
            <div className={styles.badges}><span className={`${styles.stage} ${styles[item.stage]}`}>{item.stage}</span><span>{item.role}</span></div>
          </button>)}
          {!entries.length && <div className={styles.empty}>Aucun modèle enregistré. Les nouveaux entraînements v2.24 seront enregistrés automatiquement.</div>}
        </div>
      </section>

      <section className={styles.panel}>
        <header><h3>Lifecycle</h3>{detail && <code>{detail.model_id?.slice(0, 8)}…</code>}</header>
        {!detail ? <div className={styles.empty}>Sélectionnez un modèle.</div> : <>
          <div className={styles.modelHead}>
            <div><span>Stage</span><strong>{STAGE_LABELS[stage] ?? stage}</strong></div>
            <div><span>Rôle</span><strong>{detail.role}</strong></div>
            <div><span>Version Registry</span><strong>v{detail.version_no}</strong></div>
            <div><span>Métrique</span><strong>{detail.card?.primary_metric ?? '—'} · {fmt(detail.card?.metrics_final_test?.[detail.card?.primary_metric])}</strong></div>
          </div>
          <div className={styles.hashes}><small>Artefact SHA256</small><code>{detail.artifact_sha256}</code><small>Model Card SHA256</small><code>{detail.card_sha256}</code></div>
          <div className={styles.actions}>
            {stage === 'draft' && <button onClick={() => void transition('staging')}>Passer en staging</button>}
            {stage === 'staging' && <><button onClick={() => void transition('draft')}>Retour draft</button><button className={styles.primary} onClick={() => void transition('production')}>Promouvoir en production</button></>}
            {stage === 'production' && <button className={styles.danger} onClick={() => void transition('retired')}>Retirer de production</button>}
            {stage === 'retired' && <button onClick={() => void transition('staging')}>Réactiver en staging</button>}
          </div>
          <div className={styles.governanceNote}>En Enterprise, la promotion en production exige une certification active. Un Responsible AI Gate enregistré comme bloqué interdit également la promotion.</div>
        </>}
      </section>
    </div>

    {detail && <>
      <section className={styles.panel}>
        <header><h3>Monitoring continu</h3><span>{monitoring.length} run(s)</span></header>
        <div className={styles.monitorForm}>
          <label>Dataset courant<select value={monitorDatasetId} onChange={event => setMonitorDatasetId(event.target.value)}><option value="">Sélectionner…</option>{catalog.filter(item => String(item.dataset_id ?? item.id) !== String(detail.card?.dataset?.id)).map(item => <option key={item.dataset_id ?? item.id} value={item.dataset_id ?? item.id}>{item.name ?? item.dataset_name ?? item.dataset_id} · v{item.version ?? '—'}</option>)}</select></label>
          <button className={styles.primary} disabled={!monitorDatasetId || busy === 'monitor'} onClick={() => void monitor()}>{busy === 'monitor' ? 'Monitoring…' : 'Lancer le monitoring'}</button>
        </div>
        {monitorSchedule && <div className={styles.scheduleRow}>
          <label><input type="checkbox" checked={Boolean(monitorSchedule.enabled)} onChange={event => setMonitorSchedule({ ...monitorSchedule, enabled: event.target.checked })}/> Monitoring périodique</label>
          <label>Intervalle (minutes)<input type="number" min={15} max={43200} value={monitorSchedule.interval_minutes ?? 1440} onChange={event => setMonitorSchedule({ ...monitorSchedule, interval_minutes: Number(event.target.value) })}/></label>
          <button disabled={!monitorDatasetId || busy === 'schedule'} onClick={() => void saveSchedule()}>{busy === 'schedule' ? 'Enregistrement…' : 'Enregistrer le planning'}</button>
          {monitorSchedule.next_run_at && <small>Prochain run : {new Date(monitorSchedule.next_run_at).toLocaleString('fr-FR')}</small>}
        </div>}
        {currentRun && <div className={styles.monitorGrid}>
          <div><span>Statut</span><b className={currentRun.status === 'degraded' ? styles.bad : styles.good}>{currentRun.status}</b></div>
          <div><span>Dégradation métrique</span><b>{currentRun.degradation?.relative_metric_degradation == null ? '—' : `${fmt(currentRun.degradation.relative_metric_degradation * 100, 1)} %`}</b></div>
          <div><span>Drift feature max</span><b>{fmt(currentRun.degradation?.max_feature_drift_score)}</b></div>
          <div><span>Lignes évaluées</span><b>{currentRun.rows_evaluated}</b></div>
        </div>}
        {driftRows.length > 0 && <div className={styles.tableWrap}><table><thead><tr><th>Feature</th><th>Type</th><th>Score drift</th><th>Détail</th></tr></thead><tbody>{driftRows.slice(0, 12).map((row: AnyObj) => <tr key={row.feature}><td>{row.feature}</td><td>{row.type}</td><td>{fmt(row.score)}</td><td>{row.type === 'numeric' ? `moy. ${fmt(row.reference_mean)} → ${fmt(row.current_mean)}` : `TVD ${fmt(row.tvd)}`}</td></tr>)}</tbody></table></div>}
        {currentRun?.degradation?.blockers?.length > 0 && <div className={styles.blockers}>{currentRun.degradation.blockers.map((item: AnyObj, index: number) => <span key={index}>{item.code} · {fmt(item.value)} / seuil {fmt(item.threshold)}</span>)}</div>}
      </section>

      <section className={styles.panel}>
        <header><h3>Politique de réentraînement</h3><span>demande traçable, jamais entraînement silencieux</span></header>
        {policy && <div className={styles.policyGrid}>
          <label className={styles.check}><input type="checkbox" checked={Boolean(policy.enabled)} onChange={event => setPolicy({ ...policy, enabled: event.target.checked })}/> Activer la politique</label>
          <label>Lignes minimum<input type="number" min={10} value={policy.min_rows} onChange={event => setPolicy({ ...policy, min_rows: Number(event.target.value) })}/></label>
          <label>Dégradation métrique relative<input type="number" step="0.01" min={0} value={policy.metric_degradation_threshold} onChange={event => setPolicy({ ...policy, metric_degradation_threshold: Number(event.target.value) })}/></label>
          <label>Seuil drift feature<input type="number" step="0.01" min={0} value={policy.feature_drift_threshold} onChange={event => setPolicy({ ...policy, feature_drift_threshold: Number(event.target.value) })}/></label>
          <label>Cooldown (heures)<input type="number" min={0} value={policy.cooldown_hours} onChange={event => setPolicy({ ...policy, cooldown_hours: Number(event.target.value) })}/></label>
          <label className={styles.check}><input type="checkbox" checked={Boolean(policy.auto_create_request)} onChange={event => setPolicy({ ...policy, auto_create_request: event.target.checked })}/> Créer une demande si déclenchée</label>
        </div>}
        <div className={styles.actions}><button disabled={busy === 'policy'} onClick={() => void savePolicy()}>Enregistrer la politique</button><button className={styles.primary} disabled={busy === 'retrain'} onClick={() => void checkRetraining()}>{busy === 'retrain' ? 'Évaluation…' : 'Évaluer le réentraînement'}</button></div>
        {requests.length > 0 && <div className={styles.requests}><h4>Demandes récentes</h4>{requests.slice(0, 8).map(item => <article key={item.id}><div><b>{item.status}</b><small>{new Date(item.requested_at).toLocaleString('fr-FR')}</small></div><span>{(item.reasons ?? []).map((reason: AnyObj) => reason.code).join(' · ')}</span></article>)}</div>}
      </section>

      <section className={styles.panel}>
        <header><h3>Historique Registry</h3><span>{detail.events?.length ?? 0} événement(s)</span></header>
        <div className={styles.events}>{(detail.events ?? []).slice(0, 20).map((event: AnyObj) => <article key={event.id}><b>{event.action}</b><span>{event.from_stage ?? '—'} → {event.to_stage ?? '—'}</span><small>{new Date(event.created_at).toLocaleString('fr-FR')}</small></article>)}</div>
      </section>
    </>}
  </div>;
}
