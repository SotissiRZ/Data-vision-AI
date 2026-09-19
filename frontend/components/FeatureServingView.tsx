'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  batchScoreModel,
  createFeatureSet,
  createModelDeployment,
  getFeatureSets,
  getModelDeploymentMetrics,
  getModelDeployments,
  getModelFeatureContract,
  getModelRegistryEntries,
  materializeFeatureSet,
  rollbackModelDeployment,
  scoreModelDeployment,
  setFeatureSetStatus,
  updateModelDeployment,
} from '../lib/api';
import styles from './FeatureServingView.module.css';

type AnyObj = Record<string, any>;

type Props = {
  activeModel: AnyObj | null;
  activeDataset: AnyObj | null;
  setError: (message: string) => void;
  onActivate?: (datasetId: string) => void;
};

function fmt(value: unknown, digits = 3) {
  if (typeof value !== 'number') return value == null ? '—' : String(value);
  if (!Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: digits }).format(value);
}

export function FeatureServingView({
  activeModel,
  activeDataset,
  setError,
  onActivate,
}: Props) {
  const [featureSets, setFeatureSets] = useState<AnyObj[]>([]);
  const [registry, setRegistry] = useState<AnyObj[]>([]);
  const [deployments, setDeployments] = useState<AnyObj[]>([]);
  const [selectedDeployment, setSelectedDeployment] = useState('');
  const [metrics, setMetrics] = useState<AnyObj | null>(null);
  const [contract, setContract] = useState<AnyObj | null>(null);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');

  const [featureName, setFeatureName] = useState('features');
  const [featureColumns, setFeatureColumns] = useState<string[]>([]);
  const [entityKeys, setEntityKeys] = useState<string[]>([]);
  const [eventTime, setEventTime] = useState('');

  const [deploymentName, setDeploymentName] = useState('Production API');
  const [endpointKey, setEndpointKey] = useState('production-model');
  const [primaryModel, setPrimaryModel] = useState('');
  const [secondaryModel, setSecondaryModel] = useState('');
  const [strategy, setStrategy] = useState<'champion' | 'shadow' | 'canary'>('champion');
  const [traffic, setTraffic] = useState(10);
  const [scoreText, setScoreText] = useState('[\n  {}\n]');
  const [scoreResult, setScoreResult] = useState<AnyObj | null>(null);

  const columns = activeDataset?.profile?.columns ?? activeDataset?.columns ?? [];
  const columnNames = columns.map((item: AnyObj) => String(item.name));
  const selected = useMemo(
    () => deployments.find(item => item.id === selectedDeployment) ?? null,
    [deployments, selectedDeployment],
  );

  const champions = registry.filter(
    item => item.stage === 'production' && item.role === 'champion',
  );
  const challengers = registry.filter(
    item => item.stage === 'staging' || item.stage === 'production',
  );

  async function load() {
    setError('');
    try {
      const [features, models, serving] = await Promise.all([
        getFeatureSets(),
        getModelRegistryEntries(),
        getModelDeployments(),
      ]);
      setFeatureSets(features.feature_sets ?? []);
      setRegistry(models.models ?? []);
      setDeployments(serving.deployments ?? []);
      const preferredModel =
        primaryModel
        || activeModel?.model_id
        || (models.models ?? []).find(
          (item: AnyObj) => item.stage === 'production' && item.role === 'champion',
        )?.model_id
        || '';
      if (preferredModel) setPrimaryModel(preferredModel);
      const preferredDeployment =
        selectedDeployment || (serving.deployments ?? [])[0]?.id || '';
      if (preferredDeployment) setSelectedDeployment(preferredDeployment);
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    }
  }

  useEffect(() => { void load(); }, [activeModel?.model_id, activeDataset?.id]);

  useEffect(() => {
    if (!primaryModel) {
      setContract(null);
      return;
    }
    getModelFeatureContract(primaryModel)
      .then(next => {
        setContract(next);
        const example: AnyObj = {};
        for (const item of next.schema ?? []) {
          example[item.name] =
            item.family === 'numeric'
              ? 0
              : item.family === 'boolean'
                ? false
                : '';
        }
        setScoreText(JSON.stringify([example], null, 2));
      })
      .catch(() => setContract(null));
  }, [primaryModel]);

  useEffect(() => {
    if (!selectedDeployment) {
      setMetrics(null);
      return;
    }
    getModelDeploymentMetrics(selectedDeployment, 200)
      .then(setMetrics)
      .catch(() => setMetrics(null));
  }, [selectedDeployment]);

  useEffect(() => {
    if (!featureColumns.length && columnNames.length) {
      setFeatureColumns(columnNames.slice(0, Math.min(8, columnNames.length)));
    }
  }, [activeDataset?.id]);

  async function createFeatures() {
    if (!activeDataset?.id || !featureName.trim() || !featureColumns.length) return;
    setBusy('feature-create'); setNotice(''); setError('');
    try {
      await createFeatureSet({
        name: featureName.trim(),
        source_dataset_id: activeDataset.id,
        features: featureColumns.filter(name => !entityKeys.includes(name)),
        entity_keys: entityKeys,
        event_time_column: eventTime || null,
      });
      setNotice('Feature Set créé en draft.');
      await load();
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    } finally { setBusy(''); }
  }

  async function materialize(item: AnyObj) {
    setBusy(`materialize:${item.id}`); setNotice(''); setError('');
    try {
      const result = await materializeFeatureSet(item.id, activeDataset?.id ?? null);
      setNotice(`Snapshot créé : ${result.row_count} lignes.`);
      if (result.materialized_dataset_id && onActivate) {
        onActivate(result.materialized_dataset_id);
      }
      await load();
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    } finally { setBusy(''); }
  }

  async function createDeployment() {
    if (!primaryModel || !endpointKey.trim()) return;
    setBusy('deployment-create'); setNotice(''); setError('');
    try {
      const result = await createModelDeployment({
        name: deploymentName.trim() || endpointKey.trim(),
        endpoint_key: endpointKey.trim(),
        primary_model_id: primaryModel,
        strategy,
        secondary_model_id: strategy === 'champion' ? null : secondaryModel || null,
        traffic_percent: strategy === 'canary' ? traffic : 0,
        status: 'active',
      });
      setNotice('Deployment interne créé.');
      await load();
      setSelectedDeployment(result.id);
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    } finally { setBusy(''); }
  }

  async function updateSelected(next: Partial<{
    strategy: 'champion' | 'shadow' | 'canary';
    secondary_model_id: string | null;
    traffic_percent: number;
    status: 'active' | 'inactive';
  }>) {
    if (!selectedDeployment) return;
    setBusy('deployment-update'); setNotice(''); setError('');
    try {
      await updateModelDeployment(selectedDeployment, {
        ...next,
        reason: 'ui_update',
      });
      setNotice('Deployment mis à jour.');
      await load();
      setMetrics(await getModelDeploymentMetrics(selectedDeployment, 200));
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    } finally { setBusy(''); }
  }

  async function score() {
    if (!selected?.endpoint_key) return;
    setBusy('score'); setNotice(''); setError('');
    try {
      const parsed = JSON.parse(scoreText);
      const rows = Array.isArray(parsed) ? parsed : [parsed];
      const result = await scoreModelDeployment(selected.endpoint_key, { rows });
      setScoreResult(result);
      setNotice('Scoring terminé via le serving interne DataVision.');
      setMetrics(await getModelDeploymentMetrics(selected.id, 200));
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    } finally { setBusy(''); }
  }

  async function rollback() {
    if (!selectedDeployment) return;
    setBusy('rollback'); setNotice(''); setError('');
    try {
      await rollbackModelDeployment(selectedDeployment);
      setNotice('Rollback gouverné effectué vers la révision précédente.');
      await load();
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    } finally { setBusy(''); }
  }

  async function batchScore() {
    if (!activeModel?.model_id || !activeDataset?.id) return;
    setBusy('batch'); setNotice(''); setError('');
    try {
      const result = await batchScoreModel(activeModel.model_id, {
        dataset_id: activeDataset.id,
        prediction_column: 'prediction',
        background: false,
      });
      setNotice(`${result.rows_scored} lignes scorées dans une nouvelle version immuable.`);
      if (result.output_dataset?.id && onActivate) {
        onActivate(result.output_dataset.id);
      }
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : String(error));
    } finally { setBusy(''); }
  }

  return <div className={styles.page}>
    <div className={styles.titleRow}>
      <div>
        <span className={styles.eyebrow}>FEATURE STORE · TRAINING/SERVING CONSISTENCY · SHADOW · CANARY · ROLLBACK</span>
        <h1>Feature Store & Serving</h1>
        <p>Versionnez les features, imposez un contrat de serving et exposez des modèles via le backend interne DataVision. Aucun cloud deployment n’est simulé.</p>
      </div>
      <span className={styles.backend}>Backend : DataVision internal</span>
    </div>

    {notice && <div className={styles.notice}>{notice}</div>}

    <div className={styles.metrics}>
      <div><span>Feature Sets</span><b>{featureSets.length}</b></div>
      <div><span>Deployments</span><b>{deployments.length}</b></div>
      <div><span>Production champions</span><b>{champions.length}</b></div>
      <div><span>Serving requests</span><b>{metrics?.requests ?? 0}</b></div>
      <div><span>Lignes scorées</span><b>{metrics?.rows_scored ?? 0}</b></div>
      <div><span>P95</span><b>{metrics?.p95_latency_ms == null ? '—' : `${fmt(metrics.p95_latency_ms, 1)} ms`}</b></div>
    </div>

    <section className={styles.panel}>
      <header><h3>Feature Store</h3><span>Snapshots immuables, schéma hashé</span></header>
      {!activeDataset?.id
        ? <div className={styles.empty}>Chargez un dataset pour créer un Feature Set.</div>
        : <>
          <div className={styles.formGrid}>
            <label>Nom<input value={featureName} onChange={e => setFeatureName(e.target.value)}/></label>
            <label>Event time<select value={eventTime} onChange={e => setEventTime(e.target.value)}><option value="">Aucun</option>{columnNames.map(name => <option key={name}>{name}</option>)}</select></label>
          </div>
          <div className={styles.selectorBlock}>
            <b>Features</b>
            <div className={styles.checks}>{columnNames.map(name => <label key={name}><input type="checkbox" checked={featureColumns.includes(name)} onChange={e => setFeatureColumns(e.target.checked ? [...featureColumns, name] : featureColumns.filter(x => x !== name))}/>{name}</label>)}</div>
          </div>
          <div className={styles.selectorBlock}>
            <b>Entity keys</b>
            <div className={styles.checks}>{columnNames.map(name => <label key={name}><input type="checkbox" checked={entityKeys.includes(name)} onChange={e => setEntityKeys(e.target.checked ? [...entityKeys, name] : entityKeys.filter(x => x !== name))}/>{name}</label>)}</div>
          </div>
          <button className={styles.primary} disabled={busy === 'feature-create'} onClick={() => void createFeatures()}>{busy === 'feature-create' ? 'Création…' : 'Créer le Feature Set'}</button>
        </>}
      <div className={styles.list}>
        {featureSets.map(item => <article key={item.id}>
          <div><b>{item.name}</b><small>{item.status} · {item.features?.length ?? 0} features · {String(item.schema_sha256 ?? '').slice(0, 10)}…</small></div>
          <div className={styles.actions}>
            {item.status === 'draft' && <button onClick={() => void setFeatureSetStatus(item.id, 'active').then(load).catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))}>Activer</button>}
            <button disabled={busy === `materialize:${item.id}`} onClick={() => void materialize(item)}>{busy === `materialize:${item.id}` ? 'Snapshot…' : 'Matérialiser'}</button>
          </div>
        </article>)}
        {!featureSets.length && <div className={styles.empty}>Aucun Feature Set.</div>}
      </div>
    </section>

    <div className={styles.twoCol}>
      <section className={styles.panel}>
        <header><h3>Nouveau deployment interne</h3><span>champion / shadow / canary</span></header>
        <div className={styles.formGrid}>
          <label>Nom<input value={deploymentName} onChange={e => setDeploymentName(e.target.value)}/></label>
          <label>Endpoint key<input value={endpointKey} onChange={e => setEndpointKey(e.target.value)}/></label>
          <label>Champion<select value={primaryModel} onChange={e => setPrimaryModel(e.target.value)}><option value="">Sélectionner</option>{champions.map(item => <option key={item.model_id} value={item.model_id}>v{item.version_no} · {item.card?.algorithm} · {item.card?.target}</option>)}</select></label>
          <label>Stratégie<select value={strategy} onChange={e => setStrategy(e.target.value as any)}><option value="champion">Champion</option><option value="shadow">Shadow</option><option value="canary">Canary</option></select></label>
          {strategy !== 'champion' && <label>Challenger<select value={secondaryModel} onChange={e => setSecondaryModel(e.target.value)}><option value="">Sélectionner</option>{challengers.filter(item => item.model_id !== primaryModel).map(item => <option key={item.model_id} value={item.model_id}>v{item.version_no} · {item.stage} · {item.card?.algorithm}</option>)}</select></label>}
          {strategy === 'canary' && <label>Trafic challenger %<input type="number" min={0} max={100} value={traffic} onChange={e => setTraffic(Number(e.target.value))}/></label>}
        </div>
        <button className={styles.primary} disabled={busy === 'deployment-create'} onClick={() => void createDeployment()}>{busy === 'deployment-create' ? 'Création…' : 'Créer le deployment'}</button>
        <div className={styles.contract}>
          <b>Feature Contract</b>
          {contract
            ? <><span>{contract.features?.length ?? 0} features requises</span><code>{String(contract.schema_sha256).slice(0, 16)}…</code></>
            : <span>Sélectionnez un champion production.</span>}
        </div>
      </section>

      <section className={styles.panel}>
        <header><h3>Deployments</h3><span>{deployments.length}</span></header>
        <div className={styles.deployments}>
          {deployments.map(item => <button key={item.id} className={selectedDeployment === item.id ? styles.selected : ''} onClick={() => setSelectedDeployment(item.id)}>
            <div><b>{item.name}</b><small>/{item.endpoint_key} · rev {item.revision_no}</small></div>
            <div><span>{item.strategy}</span><em>{item.status}</em></div>
          </button>)}
          {!deployments.length && <div className={styles.empty}>Aucun deployment interne.</div>}
        </div>
        {selected && <div className={styles.deploymentActions}>
          <button onClick={() => void updateSelected({ status: selected.status === 'active' ? 'inactive' : 'active' })}>{selected.status === 'active' ? 'Désactiver' : 'Activer'}</button>
          <button disabled={(selected.revisions?.length ?? 0) < 2 || busy === 'rollback'} onClick={() => void rollback()}>Rollback</button>
        </div>}
      </section>
    </div>

    {selected && <section className={styles.panel}>
      <header><h3>Tester /{selected.endpoint_key}</h3><span>{selected.strategy} · {selected.primary_model_id?.slice(0, 8)}…</span></header>
      <textarea className={styles.editor} value={scoreText} onChange={e => setScoreText(e.target.value)} spellCheck={false}/>
      <div className={styles.actions}>
        <button className={styles.primary} disabled={busy === 'score'} onClick={() => void score()}>{busy === 'score' ? 'Scoring…' : 'Scorer'}</button>
        {activeModel?.model_id && activeDataset?.id && <button disabled={busy === 'batch'} onClick={() => void batchScore()}>{busy === 'batch' ? 'Batch…' : 'Batch scorer le dataset actif'}</button>}
      </div>
      {scoreResult && <pre className={styles.result}>{JSON.stringify(scoreResult, null, 2)}</pre>}
      {metrics && <div className={styles.servingStats}>
        <div><span>Requêtes</span><b>{metrics.requests}</b></div>
        <div><span>Lignes</span><b>{metrics.rows_scored}</b></div>
        <div><span>Latence moyenne</span><b>{metrics.mean_latency_ms == null ? '—' : `${fmt(metrics.mean_latency_ms, 1)} ms`}</b></div>
        <div><span>P95</span><b>{metrics.p95_latency_ms == null ? '—' : `${fmt(metrics.p95_latency_ms, 1)} ms`}</b></div>
      </div>}
      {scoreResult?.shadow && <div className={styles.shadow}><b>Shadow comparison</b><pre>{JSON.stringify(scoreResult.shadow, null, 2)}</pre></div>}
    </section>}

    <div className={styles.warning}>
      <b>Limite de déploiement v2.25</b>
      <span>Ces endpoints sont servis par l’API DataVision installée. Kubernetes, Vertex AI, SageMaker ou un gateway externe ne sont pas déclarés comme déployés tant qu’un backend dédié n’est pas configuré.</span>
    </div>
  </div>;
}
