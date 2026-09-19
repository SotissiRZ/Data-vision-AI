'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  runModelFairnessAudit,
  runModelPopulationDrift,
  runModelResponsibleAIGate,
  runModelResponsibleAIRisk,
} from '../lib/api';
import styles from './ResponsibleAIView.module.css';

type AnyObj = Record<string, any>;

function fmt(value: unknown, digits = 3) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return value == null ? '—' : String(value);
  return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: digits }).format(value);
}

function MiniTable({ rows, columns }: { rows: AnyObj[]; columns: [string, string][] }) {
  if (!rows?.length) return <div className={styles.note}>Aucune ligne comparable.</div>;
  return <div className={styles.tableWrap}><table className={styles.table}><thead><tr>{columns.map(([, label]) => <th key={label}>{label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map(([key]) => <td key={key}>{typeof row[key] === 'number' ? fmt(row[key], 4) : row[key] == null ? '—' : String(row[key])}</td>)}</tr>)}</tbody></table></div>;
}

export function ResponsibleAIView({ result, model, setError }: { result: AnyObj | null; model: AnyObj | null; setError: (message: string) => void }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [mode, setMode] = useState<'separate' | 'intersectional' | 'both'>('both');
  const [minGroup, setMinGroup] = useState(20);
  const [positiveLabel, setPositiveLabel] = useState('');
  const [fairness, setFairness] = useState<AnyObj | null>(null);
  const [gate, setGate] = useState<AnyObj | null>(null);
  const [risk, setRisk] = useState<AnyObj | null>(null);
  const [drift, setDrift] = useState<AnyObj | null>(null);
  const [busy, setBusy] = useState('');
  const [blockFeature, setBlockFeature] = useState(false);
  const [parityDiff, setParityDiff] = useState('');
  const [selectionRatio, setSelectionRatio] = useState('');
  const [opportunityDiff, setOpportunityDiff] = useState('');
  const [fprDiff, setFprDiff] = useState('');
  const [maeRatio, setMaeRatio] = useState('');
  const [rmseRatio, setRmseRatio] = useState('');

  const columns = result?.profile?.columns ?? [];
  const target = model?.target ?? model?.model_card?.target;
  const referenceDatasetId = model?.model_card?.dataset?.id;
  const currentDatasetId = result?.dataset?.id;
  const driftPossible = Boolean(referenceDatasetId && currentDatasetId && referenceDatasetId !== currentDatasetId);

  useEffect(() => {
    setSelected([]);
    setFairness(null);
    setGate(null);
    setRisk(null);
    setDrift(null);
    setPositiveLabel('');
  }, [model?.model_id, result?.dataset?.id]);

  const policy = useMemo(() => {
    const out: AnyObj = { block_on_protected_feature_usage: blockFeature };
    const map: [string, string][] = [
      ['max_demographic_parity_difference', parityDiff],
      ['min_selection_rate_ratio', selectionRatio],
      ['max_equal_opportunity_difference', opportunityDiff],
      ['max_false_positive_rate_difference', fprDiff],
      ['max_mae_ratio', maeRatio],
      ['max_rmse_ratio', rmseRatio],
    ];
    for (const [key, raw] of map) if (raw.trim() !== '') out[key] = Number(raw);
    return out;
  }, [blockFeature, parityDiff, selectionRatio, opportunityDiff, fprDiff, maeRatio, rmseRatio]);

  if (!model) return <div className={styles.empty}><h3>Responsible AI</h3><p>Entraînez ou sélectionnez d’abord un modèle.</p></div>;
  if (!result) return <div className={styles.empty}><h3>Responsible AI</h3><p>Activez le dataset lié au modèle.</p></div>;

  function payloadBase() {
    return {
      protected_columns: selected,
      positive_label: positiveLabel.trim() === '' ? null : positiveLabel,
      mode,
      min_group_size: minGroup,
    };
  }

  async function audit() {
    if (!selected.length) return setError('Sélectionnez au moins une variable de groupe à auditer.');
    setBusy('audit'); setError('');
    try {
      const value = await runModelFairnessAudit(model.model_id, { ...payloadBase(), persist_summary: false });
      setFairness(value); setGate(null);
    } catch (error: unknown) { setError(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(''); }
  }

  async function assessRisk() {
    setBusy('risk'); setError('');
    try {
      const value = await runModelResponsibleAIRisk(model.model_id, { ...payloadBase(), protected_columns: selected, persist_summary: false });
      setRisk(value.risk); if (value.fairness) setFairness(value.fairness);
    } catch (error: unknown) { setError(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(''); }
  }

  async function publicationGate() {
    if (!selected.length) return setError('Sélectionnez au moins une variable de groupe avant le gate de publication.');
    setBusy('gate'); setError('');
    try {
      const value = await runModelResponsibleAIGate(model.model_id, { ...payloadBase(), policy, persist_summary: true });
      setGate(value); setFairness(value.fairness); setRisk(value.risk);
    } catch (error: unknown) { setError(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(''); }
  }

  async function monitorDrift() {
    if (!driftPossible || !selected.length) return;
    setBusy('drift'); setError('');
    try {
      setDrift(await runModelPopulationDrift(model.model_id, { ...payloadBase(), current_dataset_id: currentDatasetId }));
    } catch (error: unknown) { setError(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(''); }
  }

  const flatGroups = (fairness?.reports ?? []).flatMap((view: AnyObj) => (view.groups ?? []).map((group: AnyObj) => ({ view: view.view, ...group })));
  const parityRows = (fairness?.reports ?? []).map((view: AnyObj) => ({ view: view.view, ...(view.parity_metrics ?? {}) }));

  return <div className={styles.root}>
    <div className={styles.header}><div><span className={styles.eyebrow}>RESPONSIBLE AI · GROUP PERFORMANCE · MODEL RISK</span><h1>Responsible AI & Fairness</h1><p>Mesurez les performances par groupes explicitement choisis, surveillez les écarts de population et appliquez des seuils de publication définis par votre organisation. DataVision ne déduit jamais automatiquement les caractéristiques sensibles et ne transforme pas ces métriques en verdict universel.</p></div><span className={styles.badge}>Model {String(model.model_id).slice(0, 8)}…</span></div>

    <section className={styles.panel}><div className={styles.panelHead}><h3>Configuration de l’audit</h3><span className={styles.pill}>holdout final</span></div><div className={styles.panelBody}>
      <div className={styles.grid}>
        <label className={styles.field}>Mode<select value={mode} onChange={e => setMode(e.target.value as any)}><option value="separate">Chaque variable séparément</option><option value="intersectional">Intersection uniquement</option><option value="both">Séparé + intersectionnel</option></select></label>
        <label className={styles.field}>Effectif minimum<input type="number" min={2} value={minGroup} onChange={e => setMinGroup(Math.max(2, Number(e.target.value) || 2))}/></label>
        {model.task === 'classification' && <label className={styles.field}>Classe positive<input value={positiveLabel} onChange={e => setPositiveLabel(e.target.value)} placeholder="vide = auto si binaire"/></label>}
      </div>
      <div className={styles.sectionTitle}>Variables de groupe — sélection explicite, maximum 3</div>
      <div className={styles.columns}>{columns.filter((column: AnyObj) => column.name !== target).map((column: AnyObj) => <label key={column.name}><input type="checkbox" checked={selected.includes(column.name)} onChange={e => setSelected(current => e.target.checked ? [...current, column.name].slice(0, 3) : current.filter(value => value !== column.name))}/>{column.name}</label>)}</div>
      <div className={styles.buttons}><button className={styles.primary} disabled={busy === 'audit'} onClick={audit}>{busy === 'audit' ? 'Calcul…' : 'Auditer les groupes'}</button><button className={styles.secondary} disabled={busy === 'risk'} onClick={assessRisk}>{busy === 'risk' ? 'Évaluation…' : 'Évaluer le risque modèle'}</button>{driftPossible && <button className={styles.secondary} disabled={busy === 'drift' || !selected.length} onClick={monitorDrift}>{busy === 'drift' ? 'Monitoring…' : 'Comparer avec le dataset actif'}</button>}</div>
      <div className={styles.note}>Les variables choisies servent uniquement à l’audit de groupe. Elles peuvent être absentes des features du modèle. Si elles sont utilisées comme features, DataVision le signale explicitement.</div>
    </div></section>

    {risk && <div className={styles.metrics}><div className={styles.metric}><span>Risque modèle</span><b className={(styles as AnyObj)[`risk${String(risk.risk_level).charAt(0).toUpperCase()}${String(risk.risk_level).slice(1)}`]}>{risk.risk_level}</b></div><div className={styles.metric}><span>Revue requise</span><b>{risk.review_required ? 'Oui' : 'Non'}</b></div><div className={styles.metric}><span>Facteurs</span><b>{risk.factors?.length ?? 0}</b></div><div className={styles.metric}><span>Tâche</span><b>{risk.task}</b></div></div>}

    {fairness && <>
      <section className={styles.panel}><div className={styles.panelHead}><h3>Performance par groupe</h3><span className={styles.pill}>{fairness.rows_evaluated} lignes · {fairness.evaluation_source}</span></div><div className={styles.panelBody}><MiniTable rows={flatGroups} columns={fairness.task === 'classification' ? [['view','Vue'],['group','Groupe'],['support','N'],['accuracy','Accuracy'],['selection_rate','Selection rate'],['true_positive_rate','TPR'],['false_positive_rate','FPR'],['brier_score','Brier']] : [['view','Vue'],['group','Groupe'],['support','N'],['mae','MAE'],['rmse','RMSE'],['mean_error','Erreur moyenne'],['r2','R²']]}/>{fairness.protected_feature_usage?.length > 0 && <div className={styles.warning}>Variables d’audit aussi utilisées comme features : {fairness.protected_feature_usage.join(', ')}.</div>}</div></section>
      <section className={styles.panel}><div className={styles.panelHead}><h3>Écarts synthétiques</h3></div><div className={styles.panelBody}><MiniTable rows={parityRows} columns={fairness.task === 'classification' ? [['view','Vue'],['demographic_parity_difference','Δ sélection'],['selection_rate_ratio','Ratio sélection'],['equal_opportunity_difference','Δ TPR'],['false_positive_rate_difference','Δ FPR'],['equalized_odds_difference','Equalized odds Δ']] : [['view','Vue'],['mae_difference','Δ MAE'],['mae_ratio','Ratio MAE'],['rmse_difference','Δ RMSE'],['rmse_ratio','Ratio RMSE']]}/><div className={styles.note}>{fairness.threshold_policy}</div></div></section>
    </>}

    <section className={styles.panel}><div className={styles.panelHead}><h3>Publication gate — politique de l’organisation</h3></div><div className={styles.panelBody}>
      <div className={styles.policyGrid}>
        {model.task === 'classification' ? <><label className={styles.field}>Max Δ sélection<input value={parityDiff} onChange={e => setParityDiff(e.target.value)} placeholder="non imposé"/></label><label className={styles.field}>Min ratio sélection<input value={selectionRatio} onChange={e => setSelectionRatio(e.target.value)} placeholder="non imposé"/></label><label className={styles.field}>Max Δ TPR<input value={opportunityDiff} onChange={e => setOpportunityDiff(e.target.value)} placeholder="non imposé"/></label><label className={styles.field}>Max Δ FPR<input value={fprDiff} onChange={e => setFprDiff(e.target.value)} placeholder="non imposé"/></label></> : <><label className={styles.field}>Max ratio MAE<input value={maeRatio} onChange={e => setMaeRatio(e.target.value)} placeholder="non imposé"/></label><label className={styles.field}>Max ratio RMSE<input value={rmseRatio} onChange={e => setRmseRatio(e.target.value)} placeholder="non imposé"/></label></>}
      </div>
      <label className={styles.checkLine}><input type="checkbox" checked={blockFeature} onChange={e => setBlockFeature(e.target.checked)}/>Bloquer la publication si une variable d’audit sélectionnée est utilisée comme feature.</label>
      <div className={styles.buttons}><button className={styles.primary} disabled={busy === 'gate' || !selected.length} onClick={publicationGate}>{busy === 'gate' ? 'Vérification…' : 'Exécuter le publication gate'}</button></div>
      <div className={styles.note}>Les seuils ci-dessus sont optionnels et propres à votre organisation. DataVision n’applique aucun seuil statistique comme définition universelle de l’équité.</div>
    </div></section>

    {gate && <><div className={gate.allowed ? styles.gateOpen : styles.gateBlocked}>{gate.allowed ? 'PUBLICATION GATE OUVERT' : `PUBLICATION BLOQUÉE · ${gate.blockers?.length ?? 0} bloqueur(s)`}</div>{gate.blockers?.length > 0 && <section className={styles.panel}><div className={styles.panelHead}><h3>Bloqueurs</h3></div><div className={styles.panelBody}><MiniTable rows={gate.blockers} columns={[['code','Code'],['view','Vue'],['metric','Métrique'],['value','Valeur'],['operator','Règle'],['threshold','Seuil']]}/></div></section>}</>}

    {drift && <section className={styles.panel}><div className={styles.panelHead}><h3>Population drift</h3><span className={styles.pill}>{drift.labels_available_in_current ? 'labels disponibles' : 'distribution uniquement'}</span></div><div className={styles.panelBody}><div className={styles.driftGrid}>{(drift.representation_drift ?? []).map((view: AnyObj) => <div key={view.view}><div className={styles.sectionTitle}>{view.view} · max shift {fmt(view.max_absolute_share_shift, 4)}</div><MiniTable rows={view.groups ?? []} columns={[['group','Groupe'],['reference_share','Part référence'],['current_share','Part actuelle'],['share_delta','Δ part']]}/></div>)}</div></div></section>}
  </div>;
}
