'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  getColumnAnalysis, getDataset, getDecision, getPreview, getProfile, getQuality, getVersions,
  predictModel, runAnova, runClustering, runPca, runRegression, transformDataset,
  trainModel, uploadDataset, getDatasetCatalog, combineDataset, getPipelines, savePipeline, runPipeline,
  runCorrelations, runStatisticalTest, getTestAdvice, getEngineInfo, runSql, recommendVisualizations, buildVisualization, runAutoML,
  runForecast, runAnomalyDetection, getModelDiagnostics, explainModelPrediction, getAIAnalystCapabilities, runAIAnalysis,
} from '../lib/api';

type AnyObj = Record<string, any>;
type View = 'home' | 'data' | 'stats' | 'tests' | 'quality' | 'prepare' | 'visual' | 'sql' | 'regression' | 'anova' | 'pca' | 'cluster' | 'model' | 'forecast' | 'anomaly' | 'xai' | 'predict' | 'ai' | 'report';

const nav: { key: View; label: string; icon: string; status?: 'partial' | 'planned' }[] = [
  { key: 'home', label: 'Accueil', icon: '⌂' },
  { key: 'data', label: 'Données', icon: '▦' },
  { key: 'stats', label: 'Statistiques descriptives', icon: '▤' },
  { key: 'tests', label: 'Tests & corrélations', icon: '∑' },
  { key: 'quality', label: 'Qualité des données', icon: '✓' },
  { key: 'prepare', label: 'Préparation', icon: '⌘' },
  { key: 'visual', label: 'Visualisation Studio', icon: '▥' },
  { key: 'sql', label: 'SQL Workspace', icon: '⌗' },
  { key: 'regression', label: 'Régression', icon: '↗' },
  { key: 'anova', label: 'ANOVA', icon: '≋' },
  { key: 'pca', label: 'ACP', icon: '◔' },
  { key: 'cluster', label: 'Clustering', icon: '◫' },
  { key: 'model', label: 'Modélisation', icon: '◆' },
  { key: 'forecast', label: 'Forecasting', icon: '⌁' },
  { key: 'anomaly', label: 'Anomalies', icon: '⚠' },
  { key: 'xai', label: 'Explicabilité XAI', icon: '◇' },
  { key: 'predict', label: 'Prédictions', icon: '◎' },
  { key: 'ai', label: 'AI Analyst', icon: '✦' },
  { key: 'report', label: 'Rapports', icon: '▧', status: 'planned' },
];

function formatNumber(value: unknown, digits = 3) {
  if (typeof value !== 'number') return value == null ? '—' : String(value);
  if (!Number.isFinite(value)) return '—';
  if (Math.abs(value) > 0 && Math.abs(value) < 0.001) return value.toExponential(2);
  return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: digits }).format(value);
}
function pText(v: unknown) { return typeof v === 'number' ? (v < 0.001 ? '< 0,001' : formatNumber(v, 4)) : '—'; }
function isNumeric(c: AnyObj) { return /int|float|double|decimal/i.test(c.dtype); }
function Stat({ label, value, detail }: { label: string; value: React.ReactNode; detail?: React.ReactNode }) {
  return <div className="metric-card"><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>;
}
function Panel({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return <section className="panel"><header className="panel-head"><h3>{title}</h3>{action}</header><div className="panel-body">{children}</div></section>;
}
function EmptyState({ title, text }: { title: string; text: string }) {
  return <div className="empty-state"><div className="empty-icon">↥</div><h3>{title}</h3><p>{text}</p></div>;
}
function RunButton({ busy, label, busyLabel, onClick }: { busy: boolean; label: string; busyLabel: string; onClick: () => void }) {
  return <button className="primary-btn real-button" disabled={busy} onClick={onClick}>{busy ? busyLabel : `▶ ${label}`}</button>;
}

export default function Home() {
  const [view, setView] = useState<View>('home');
  const [result, setResult] = useState<AnyObj | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [selectedColumn, setSelectedColumn] = useState('');
  const [columnAnalysis, setColumnAnalysis] = useState<AnyObj | null>(null);
  const [model, setModel] = useState<AnyObj | null>(null);
  const [target, setTarget] = useState('');
  const [algorithm, setAlgorithm] = useState('auto');
  const [training, setTraining] = useState(false);
  const [automlRunning, setAutomlRunning] = useState(false);
  const [predictionText, setPredictionText] = useState('[\n  {}\n]');
  const [prediction, setPrediction] = useState<AnyObj | null>(null);
  const [predicting, setPredicting] = useState(false);

  async function activateDataset(id: string, nextView?: View) {
    setBusy(true); setError(''); setModel(null); setPrediction(null); setColumnAnalysis(null);
    try {
      const [dataset, profile, quality, decision, preview, versions] = await Promise.all([
        getDataset(id), getProfile(id), getQuality(id), getDecision(id), getPreview(id, 25), getVersions(id),
      ]);
      const complete = { dataset, profile, quality, decision, preview, versions };
      setResult(complete);
      const firstNumeric = profile.columns.find((c: AnyObj) => isNumeric(c))?.name ?? profile.columns[0]?.name ?? '';
      setSelectedColumn(firstNumeric);
      setTarget(profile.columns[profile.columns.length - 1]?.name ?? '');
      if (nextView) setView(nextView);
      return complete;
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); return null; }
    finally { setBusy(false); }
  }

  async function onFile(file?: File) {
    if (!file) return;
    setBusy(true); setError('');
    try {
      const uploaded = await uploadDataset(file);
      await activateDataset(uploaded.dataset.id, 'data');
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  function acceptTransformed(next: AnyObj) {
    const complete = { dataset: next.dataset, profile: next.profile, quality: next.quality, decision: next.decision, preview: next.preview, versions: next.versions };
    setResult(complete);
    setModel(null); setPrediction(null); setColumnAnalysis(null);
    const firstNumeric = next.profile.columns.find((c: AnyObj) => isNumeric(c))?.name ?? next.profile.columns[0]?.name ?? '';
    setSelectedColumn(firstNumeric);
    setTarget(next.profile.columns[next.profile.columns.length - 1]?.name ?? '');
  }

  useEffect(() => {
    if (!result || !selectedColumn || view !== 'stats') return;
    let cancelled = false;
    setColumnAnalysis(null);
    getColumnAnalysis(result.dataset.id, selectedColumn)
      .then(data => { if (!cancelled) setColumnAnalysis(data); })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [result, selectedColumn, view]);

  async function doTrain() {
    if (!result || !target) return;
    setTraining(true); setError('');
    try {
      const trained = await trainModel(result.dataset.id, { target, task: 'auto', algorithm });
      setModel(trained);
      const features = result.profile.columns.filter((c: AnyObj) => c.name !== target).slice(0, 4).reduce((acc: AnyObj, c: AnyObj) => { acc[c.name] = null; return acc; }, {});
      setPredictionText(JSON.stringify([features], null, 2)); setView('predict');
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setTraining(false); }
  }
  async function doAutoML(config: { primary_metric: string; cv_folds: number; tune: boolean; max_candidates: number }) {
    if (!result || !target) return;
    setAutomlRunning(true); setError('');
    try {
      const trained = await runAutoML(result.dataset.id, { target, task: 'auto', ...config });
      setModel(trained);
      const features = result.profile.columns.filter((c: AnyObj) => c.name !== target).slice(0, 6).reduce((acc: AnyObj, c: AnyObj) => { acc[c.name] = null; return acc; }, {});
      setPredictionText(JSON.stringify([features], null, 2));
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setAutomlRunning(false); }
  }

  async function doPredict() {
    if (!model) return;
    setPredicting(true); setError('');
    try {
      const rows = JSON.parse(predictionText);
      if (!Array.isArray(rows)) throw new Error('Le JSON doit être un tableau d’objets.');
      setPrediction(await predictModel(model.model_id, rows));
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setPredicting(false); }
  }

  return <main className="app-shell">
    <header className="topbar">
      <div className="brand-mini"><div className="brand-mark">DV</div><div><b>DataVision AI</b><span>Data Intelligence Workspace</span></div></div>
      <div className="top-actions"><span className="runtime-dot"/> Moteur local <kbd>Ctrl K</kbd><button className="avatar">DV</button></div>
    </header>
    <div className="app-grid">
      <aside className="sidebar">
        <div className="workspace-label"><span>WORKSPACE</span><b>Analyse locale</b></div>
        <nav>{nav.map(item => <button key={item.key} className={view === item.key ? 'nav-item active' : 'nav-item'} onClick={() => setView(item.key)}><span className="nav-icon">{item.icon}</span><span>{item.label}</span>{item.status && <i className={`status-chip ${item.status}`}>{item.status === 'planned' ? 'bientôt' : 'partiel'}</i>}</button>)}</nav>
        <label className="upload-side">{busy ? 'Analyse en cours…' : '↥  Importer un fichier'}<input type="file" accept=".csv,.xlsx,.json,.parquet,.txt" onChange={e => onFile(e.target.files?.[0])}/></label>
        {result && <div className="dataset-mini"><span>DATASET ACTIF</span><b title={result.dataset.name}>{result.dataset.name}</b><small>v{result.dataset.version ?? 1} · {result.profile.rows} lignes · {result.profile.columns_count} variables</small></div>}
      </aside>
      <section className="content">
        {error && <div className="alert"><b>Erreur</b><span>{error}</span><button onClick={() => setError('')}>×</button></div>}
        {view === 'home' && <HomeView result={result} busy={busy} onFile={onFile} setView={setView}/>} 
        {view === 'data' && <DataView result={result}/>} 
        {view === 'stats' && <StatsView result={result} selectedColumn={selectedColumn} setSelectedColumn={setSelectedColumn} analysis={columnAnalysis}/>} 
        {view === 'tests' && <StatisticalLab result={result} setError={setError}/>} 
        {view === 'quality' && <QualityView result={result}/>} 
        {view === 'prepare' && <PrepareView result={result} setError={setError} onTransformed={acceptTransformed} onActivate={id => activateDataset(id, 'prepare')}/>} 
        {view === 'visual' && <VisualizationStudio result={result} setError={setError}/>} 
        {view === 'sql' && <SqlWorkspace result={result} setError={setError}/>} 
        {view === 'regression' && <RegressionView result={result} setError={setError}/>} 
        {view === 'anova' && <AnovaView result={result} setError={setError}/>} 
        {view === 'pca' && <PcaView result={result} setError={setError}/>} 
        {view === 'cluster' && <ClusterView result={result} setError={setError}/>} 
        {view === 'model' && <ModelView result={result} target={target} setTarget={setTarget} algorithm={algorithm} setAlgorithm={setAlgorithm} training={training} automlRunning={automlRunning} doTrain={doTrain} doAutoML={doAutoML} model={model}/>} 
        {view === 'forecast' && <ForecastView result={result} setError={setError}/>}
        {view === 'anomaly' && <AnomalyView result={result} setError={setError}/>}
        {view === 'xai' && <XaiView result={result} model={model} setError={setError}/>}
        {view === 'ai' && <AIAnalystView result={result} setError={setError}/>}
        {view === 'predict' && <PredictView model={model} text={predictionText} setText={setPredictionText} predicting={predicting} doPredict={doPredict} prediction={prediction}/>} 
        {view === 'report' && <PlannedView view={view}/>} 
      </section>
    </div>
  </main>;
}

function HomeView({ result, busy, onFile, setView }: { result: AnyObj | null; busy: boolean; onFile: (file?: File) => void; setView: (v: View) => void }) {
  return <div className="home-view">
    <section className="hero"><div className="hero-copy"><span className="eyebrow">DATA ANALYSIS · STATISTICS · MACHINE LEARNING</span><h1>DataVision</h1><h2>De la donnée brute à une décision vérifiable.</h2><p>Une interface fidèle à l’esprit du DataVision historique, avec des moteurs analytiques modernes et réellement exécutés.</p><div className="hero-actions"><label className="primary-btn">{busy ? 'Analyse en cours…' : 'Importer un dataset'}<input type="file" accept=".csv,.xlsx,.json,.parquet,.txt" onChange={e => onFile(e.target.files?.[0])}/></label>{result && <button className="secondary-btn" onClick={() => setView('data')}>Ouvrir le dataset actif</button>}</div></div><div className="hero-visual"><span className="bar b1"/><span className="bar b2"/><span className="bar b3"/><span className="bar b4"/><span className="line l1"/><span className="line l2"/><span className="data-orb">AI</span></div></section>
    <div className="feature-strip"><button onClick={() => setView('stats')}><span className="feature-icon red">▤</span><div><b>Analyse statistique</b><p>Descriptif, régression, ANOVA et diagnostics.</p></div></button><button onClick={() => setView('pca')}><span className="feature-icon green">◔</span><div><b>Analyse multivariée</b><p>ACP, contributions, variance et représentations.</p></div></button><button onClick={() => setView('cluster')}><span className="feature-icon orange">◫</span><div><b>Clustering & ML</b><p>K-means, silhouette, modèles et prédictions.</p></div></button></div>
    <div className="workflow"><span>CONNECTER</span><i>→</i><span>COMPRENDRE</span><i>→</i><span>PRÉPARER</span><i>→</i><span>ANALYSER</span><i>→</i><span>MODÉLISER</span><i>→</i><strong>DÉCIDER</strong></div>
  </div>;
}

function DataView({ result }: { result: AnyObj | null }) {
  if (!result) return <EmptyState title="Données" text="Importez un fichier CSV, XLSX, JSON, Parquet ou TXT pour commencer."/>;
  return <div className="page"><div className="page-title"><div><span className="eyebrow">DATASET</span><h1>{result.dataset.name}</h1><p>Aperçu du jeu de données, schéma détecté et informations de profilage.</p></div><div className="dataset-badges"><span className="version-badge">Version {result.dataset.version ?? 1}</span><span className="format-badge">{result.dataset.format.replace('.','').toUpperCase()}</span></div></div>
    <div className="metrics"><Stat label="Lignes" value={result.profile.rows}/><Stat label="Variables" value={result.profile.columns_count}/><Stat label="Doublons" value={result.profile.duplicates}/><Stat label="Mémoire" value={`${formatNumber(result.profile.memory_bytes/1024)} Ko`}/></div>
    <Panel title="Aperçu des données" action={<span className="quiet">{result.preview.shown}/{result.preview.total}</span>}><DataTable preview={result.preview}/></Panel>
    <Panel title="Variables"><div className="columns-grid">{result.profile.columns.map((c: AnyObj) => <div className="column-card" key={c.name}><b>{c.name}</b><span>{c.dtype}</span><small>{c.unique} valeurs uniques · {formatNumber(c.missing_pct)} % manquantes</small></div>)}</div></Panel>
  </div>;
}
function DataTable({ preview }: { preview: AnyObj }) {
  return <div className="table-scroll"><table><thead><tr>{preview.columns.map((c:string)=><th key={c}>{c}</th>)}</tr></thead><tbody>{preview.rows.map((r:AnyObj,i:number)=><tr key={i}>{preview.columns.map((c:string)=><td key={c}>{r[c] == null ? <span className="null">NA</span> : String(r[c])}</td>)}</tr>)}</tbody></table></div>;
}

function StatsView({ result, selectedColumn, setSelectedColumn, analysis }: { result: AnyObj | null; selectedColumn: string; setSelectedColumn: (v: string) => void; analysis: AnyObj | null }) {
  if (!result) return <EmptyState title="Statistiques descriptives" text="Chargez un dataset afin d’analyser chaque variable."/>;
  return <div className="page"><div className="page-title"><div><span className="eyebrow">STATISTIQUES DESCRIPTIVES</span><h1>Statistiques Descriptives</h1><p>Sélectionnez une variable pour afficher ses indicateurs et sa représentation graphique.</p></div></div><Panel title="Choix de la variable"><div className="form-row"><label>Choisissez une variable<select value={selectedColumn} onChange={e=>setSelectedColumn(e.target.value)}>{result.profile.columns.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><span className="field-hint">Les résultats sont recalculés par le backend.</span></div></Panel>{!analysis ? <div className="loading-card">Calcul des statistiques…</div> : analysis.kind === 'numeric' ? <NumericAnalysis analysis={analysis}/> : <CategoricalAnalysis analysis={analysis}/>}</div>;
}
function NumericAnalysis({ analysis }: { analysis: AnyObj }) { const s=analysis.summary; return <><div className="metrics six"><Stat label="Moyenne" value={formatNumber(s.mean)}/><Stat label="Médiane" value={formatNumber(s.median)}/><Stat label="Écart-type" value={formatNumber(s.std)}/><Stat label="Variance" value={formatNumber(s.variance)}/><Stat label="Minimum" value={formatNumber(s.min)}/><Stat label="Maximum" value={formatNumber(s.max)}/></div><div className="two-col"><Panel title="Histogramme"><Histogram bins={analysis.histogram}/></Panel><Panel title="Quartiles et extrêmes"><div className="summary-list"><span>Premier quartile (Q1)<b>{formatNumber(s.q1)}</b></span><span>Médiane<b>{formatNumber(s.median)}</b></span><span>Troisième quartile (Q3)<b>{formatNumber(s.q3)}</b></span><span>Valeurs aberrantes IQR<b>{s.outliers_iqr}</b></span></div></Panel></div><Panel title="Box Plot"><BoxPlot data={analysis.boxplot}/></Panel></>; }
function Histogram({ bins }: { bins: AnyObj[] }) { const max=Math.max(1,...bins.map(b=>b.count)); return <div className="histogram"><div className="hist-bars">{bins.map((b,i)=><div key={i} className="hist-slot" title={`${b.from} – ${b.to}: ${b.count}`}><span style={{height:`${Math.max(3,b.count/max*100)}%`}}/></div>)}</div><div className="axis-row"><span>{formatNumber(bins[0]?.from)}</span><span>{formatNumber(bins[Math.floor(bins.length/2)]?.from)}</span><span>{formatNumber(bins[bins.length-1]?.to)}</span></div></div>; }
function BoxPlot({ data }: { data: AnyObj }) { const min=Number(data.min),max=Number(data.max),span=Math.max(1e-9,max-min); const pct=(v:number)=>5+((v-min)/span)*90; return <div className="boxplot"><div className="box-axis"><span style={{left:`${pct(data.whisker_low)}%`}} className="whisker left"/><span style={{left:`${pct(data.whisker_high)}%`}} className="whisker right"/><span className="whisker-line" style={{left:`${pct(data.whisker_low)}%`,width:`${pct(data.whisker_high)-pct(data.whisker_low)}%`}}/><span className="box" style={{left:`${pct(data.q1)}%`,width:`${pct(data.q3)-pct(data.q1)}%`}}/><span className="median" style={{left:`${pct(data.median)}%`}}/></div><div className="box-labels"><span>{formatNumber(min)}</span><span>Q1 {formatNumber(data.q1)}</span><span>Médiane {formatNumber(data.median)}</span><span>Q3 {formatNumber(data.q3)}</span><span>{formatNumber(max)}</span></div></div>; }
function CategoricalAnalysis({ analysis }: { analysis: AnyObj }) { const max=Math.max(1,...analysis.categories.map((x:AnyObj)=>x.count)); return <Panel title="Répartition des catégories"><div className="category-chart">{analysis.categories.map((x:AnyObj)=><div className="cat-row" key={x.value}><span>{x.value}</span><div><i style={{width:`${x.count/max*100}%`}}/></div><b>{x.count} <small>({x.pct}%)</small></b></div>)}</div></Panel>; }

function QualityView({ result }: { result: AnyObj | null }) {
  if (!result) return <EmptyState title="Qualité des données" text="Chargez un dataset pour lancer automatiquement les contrôles de qualité."/>;
  return <div className="page"><div className="page-title"><div><span className="eyebrow">DATA QUALITY</span><h1>Diagnostic de qualité</h1><p>Détection déterministe des valeurs manquantes, doublons, colonnes constantes et outliers IQR.</p></div><div className={`score-ring ${result.quality.score >= 80 ? 'good' : result.quality.score >= 60 ? 'warn' : 'bad'}`}><strong>{result.quality.score}</strong><span>/100</span></div></div><div className="metrics"><Stat label="Score qualité" value={`${result.quality.score}/100`}/><Stat label="Problèmes" value={result.quality.issues_count}/><Stat label="Doublons" value={result.profile.duplicates}/><Stat label="Statut" value={result.quality.score >= 80 ? 'Bon' : result.quality.score >= 60 ? 'À revoir' : 'Critique'}/></div><Panel title="Problèmes détectés">{result.quality.issues.length===0?<div className="success-box">✓ Aucun problème détecté par les règles actuellement implémentées.</div>:<div className="issue-list">{result.quality.issues.map((i:AnyObj,idx:number)=><article key={idx} className={`issue ${i.severity}`}><span className="severity">{i.severity}</span><div><b>{i.column?`${i.column} — `:''}{i.description}</b><p>{i.impact}</p><small>Recommandation : {i.recommendation}</small></div></article>)}</div>}</Panel><Panel title="Aide à la décision"><div className="decision-list">{result.decision.actions.map((a:AnyObj,i:number)=><div key={i}><span className={`priority ${a.priority}`}>{a.priority}</span><div><b>{a.action}</b><small>Preuve : {a.evidence}</small></div></div>)}</div></Panel></div>;
}

function PrepareView({ result, setError, onTransformed, onActivate }: { result:AnyObj|null; setError:(s:string)=>void; onTransformed:(r:AnyObj)=>void; onActivate:(id:string)=>Promise<AnyObj|null> }) {
  const [operation,setOperation]=useState('fill_missing');
  const [column,setColumn]=useState('');
  const [secondColumn,setSecondColumn]=useState('');
  const [selected,setSelected]=useState<string[]>([]);
  const [selected2,setSelected2]=useState<string[]>([]);
  const [newName,setNewName]=useState('');
  const [expression,setExpression]=useState('');
  const [strategy,setStrategy]=useState('median');
  const [constant,setConstant]=useState('');
  const [dtype,setDtype]=useState('string');
  const [operator,setOperator]=useState('eq');
  const [filterValue,setFilterValue]=useState('');
  const [ascending,setAscending]=useState(true);
  const [iqrFactor,setIqrFactor]=useState(1.5);
  const [outlierMode,setOutlierMode]=useState('clip');
  const [aggFunction,setAggFunction]=useState('mean');
  const [aggAlias,setAggAlias]=useState('');
  const [pivotAgg,setPivotAgg]=useState('mean');
  const [varName,setVarName]=useState('variable');
  const [valueName,setValueName]=useState('value');
  const [dateParts,setDateParts]=useState<string[]>(['year','month']);
  const [busy,setBusy]=useState(false);
  const [switching,setSwitching]=useState('');
  const [catalog,setCatalog]=useState<AnyObj[]>([]);
  const [pipelines,setPipelines]=useState<AnyObj[]>([]);
  const [pipelineName,setPipelineName]=useState('');
  const [pipelineBusy,setPipelineBusy]=useState('');
  const [otherDataset,setOtherDataset]=useState('');
  const [otherColumns,setOtherColumns]=useState<AnyObj[]>([]);
  const [combineType,setCombineType]=useState('merge');
  const [leftKey,setLeftKey]=useState('');
  const [rightKey,setRightKey]=useState('');
  const [joinHow,setJoinHow]=useState('inner');
  const columns=result?.profile?.columns??[];
  const numeric=columns.filter(isNumeric);
  const categorical=columns.filter((c:AnyObj)=>!isNumeric(c));

  useEffect(()=>{
    if(!result) return;
    setColumn(columns[0]?.name??''); setSecondColumn(numeric[0]?.name??columns[0]?.name??''); setSelected([]); setSelected2([]); setNewName(''); setExpression('');
    Promise.all([getDatasetCatalog(),getPipelines(result.dataset.id)]).then(([c,p])=>{
      const choices=(c.datasets??[]).filter((d:AnyObj)=>d.id!==result.dataset.id);
      setCatalog(choices); setPipelines(p.pipelines??[]);
      setOtherDataset(prev=>choices.some((d:AnyObj)=>d.id===prev)?prev:(choices[0]?.id??''));
    }).catch(()=>{});
  },[result?.dataset?.id]);

  useEffect(()=>{
    if(!otherDataset){setOtherColumns([]);setRightKey('');return;}
    getProfile(otherDataset).then(p=>{setOtherColumns(p.columns??[]);setRightKey((p.columns??[])[0]?.name??'');}).catch(()=>setOtherColumns([]));
  },[otherDataset]);

  useEffect(()=>{
    if(operation==='clip_outliers_iqr' && !numeric.some((c:AnyObj)=>c.name===column)) setColumn(numeric[0]?.name??'');
  },[operation,result?.dataset?.id]);
  if(!result) return <EmptyState title="Studio de préparation" text="Chargez un dataset pour nettoyer, transformer, combiner et versionner les données sans modifier l’original."/>;

  const operationMeta:Record<string,{label:string;help:string;icon:string}>={
    fill_missing:{label:'Imputer les valeurs manquantes',help:'Moyenne, médiane, mode ou constante.',icon:'∅'},
    remove_duplicates:{label:'Supprimer les doublons',help:'Toutes les colonnes ou un sous-ensemble.',icon:'≡'},
    rename_column:{label:'Renommer une colonne',help:'Renommage traçable et versionné.',icon:'✎'},
    drop_columns:{label:'Supprimer des colonnes',help:'Retrait uniquement dans la nouvelle version.',icon:'−'},
    cast_type:{label:'Convertir le type',help:'String, entier, réel, booléen, date ou catégorie.',icon:'T'},
    filter_rows:{label:'Filtrer les lignes',help:'Filtres numériques, texte et valeurs nulles.',icon:'⌕'},
    sort_rows:{label:'Trier les lignes',help:'Tri stable croissant ou décroissant.',icon:'↕'},
    clip_outliers_iqr:{label:'Traiter les outliers IQR',help:'Écrêter ou retirer les observations aberrantes.',icon:'◇'},
    standardize:{label:'Standardiser (Z-score)',help:'Centrer et réduire les variables numériques.',icon:'σ'},
    normalize_minmax:{label:'Normaliser Min-Max',help:'Ramener les variables entre 0 et 1.',icon:'↔'},
    one_hot_encode:{label:'Encodage one-hot',help:'Créer des indicatrices pour les catégories.',icon:'01'},
    add_calculated_column:{label:'Variable calculée',help:'Feature engineering avec expression sûre.',icon:'ƒ'},
    groupby_aggregate:{label:'GroupBy & agrégation',help:'Résumer les données par groupe.',icon:'Σ'},
    pivot_table:{label:'Pivot',help:'Transformer les modalités en colonnes.',icon:'⊞'},
    melt_unpivot:{label:'Unpivot / Melt',help:'Transformer des colonnes en lignes.',icon:'⇵'},
    extract_date_parts:{label:'Composantes de date',help:'Année, trimestre, mois, jour, semaine, heure.',icon:'◷'},
  };

  async function apply(){
    setBusy(true);setError('');
    try{
      let op:AnyObj={type:operation};
      if(operation==='fill_missing') op={...op,column,strategy,...(strategy==='constant'?{value:constant}:{})};
      if(operation==='remove_duplicates') op={...op,subset:selected};
      if(operation==='rename_column') op={...op,column,new_name:newName};
      if(operation==='drop_columns') op={...op,columns:selected};
      if(operation==='cast_type') op={...op,column,dtype};
      if(operation==='filter_rows') op={...op,column,operator,...(!['is_null','not_null'].includes(operator)?{value:filterValue}:{})};
      if(operation==='sort_rows') op={...op,column,ascending};
      if(operation==='clip_outliers_iqr') op={...op,column,factor:iqrFactor,mode:outlierMode};
      if(operation==='standardize'||operation==='normalize_minmax'||operation==='one_hot_encode') op={...op,columns:selected};
      if(operation==='add_calculated_column') op={...op,new_name:newName,expression};
      if(operation==='groupby_aggregate') op={...op,group_by:selected,aggregations:[{column,function:aggFunction,alias:aggAlias||undefined}]};
      if(operation==='pivot_table') op={...op,index:selected,columns:column,values:secondColumn,aggfunc:pivotAgg};
      if(operation==='melt_unpivot') op={...op,id_vars:selected,value_vars:selected2,var_name:varName,value_name:valueName};
      if(operation==='extract_date_parts') op={...op,column,parts:dateParts};
      const next=await transformDataset(result!.dataset.id,op);
      onTransformed(next); setSelected([]); setSelected2([]); setNewName(''); setExpression('');
    }catch(e:unknown){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }

  async function combine(){
    if(!otherDataset) return setError('Chargez au moins un second dataset avant de lancer une combinaison.');
    setBusy(true);setError('');
    try{
      let op:AnyObj={type:combineType};
      if(combineType==='merge') op={...op,left_on:[leftKey||columns[0]?.name||''],right_on:[rightKey],how:joinHow};
      if(combineType==='concat_rows') op={...op,join:'outer'};
      const next=await combineDataset(result!.dataset.id,otherDataset,op);
      onTransformed(next);
    }catch(e:unknown){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }

  async function saveCurrentPipeline(){
    setPipelineBusy('save');setError('');
    try{const r=await savePipeline(result!.dataset.id,pipelineName||`Pipeline v${result!.dataset.version}`);setPipelines(r.pipelines??[]);setPipelineName('');}
    catch(e:unknown){setError(e instanceof Error?e.message:String(e));}
    finally{setPipelineBusy('');}
  }
  async function replayPipeline(id:string){
    setPipelineBusy(id);setError('');
    try{const baseId=result!.versions?.root_id??result!.dataset.root_id??result!.dataset.id;const next=await runPipeline(baseId,id);onTransformed(next);}
    catch(e:unknown){setError(e instanceof Error?e.message:String(e));}
    finally{setPipelineBusy('');}
  }
  async function activate(id:string){setSwitching(id);setError('');try{await onActivate(id);}finally{setSwitching('');}}

  const versions=result.versions?.versions??[];
  const lineage=versions.filter((v:AnyObj)=>v.in_lineage).sort((a:AnyObj,b:AnyObj)=>a.version-b.version);
  return <div className="page"><div className="page-title"><div><span className="eyebrow">DATA PREPARATION STUDIO</span><h1>Préparation, pipeline & versioning</h1><p>Nettoyage, feature engineering, agrégations et combinaisons multi-datasets avec provenance et rollback.</p></div><span className="module-state implemented">implémenté</span></div>
    <div className="metrics"><Stat label="Version active" value={`v${result.dataset.version??1}`}/><Stat label="Lignes" value={result.profile.rows}/><Stat label="Variables" value={result.profile.columns_count}/><Stat label="Étapes actives" value={Math.max(0,lineage.length-1)}/></div>

    <Panel title="Pipeline visuel de la branche active" action={<span className="quiet">rejouable · traçable</span>}><div className="pipeline-canvas">{lineage.map((v:AnyObj,i:number)=><div className="pipeline-wrap" key={v.id}><div className={v.id===result.dataset.id?'pipeline-node active':'pipeline-node'}><span>v{v.version}</span><b>{v.operation?.label??'Import source'}</b><small>{v.operation?.type??'upload'}</small></div>{i<lineage.length-1&&<div className="pipeline-arrow">→</div>}</div>)}</div></Panel>

    <div className="prep-layout">
      <Panel title="Transformations"><div className="prep-operation-list">{Object.entries(operationMeta).map(([key,m])=><button key={key} className={operation===key?'prep-op active':'prep-op'} onClick={()=>{setOperation(key);setSelected([]);setSelected2([]);}}><span>{m.icon}</span><div><b>{m.label}</b><small>{m.help}</small></div></button>)}</div></Panel>
      <Panel title={operationMeta[operation].label}><div className="analysis-config prep-config">
        {['fill_missing','rename_column','cast_type','filter_rows','sort_rows','clip_outliers_iqr','pivot_table','extract_date_parts','groupby_aggregate'].includes(operation)&&<label>{operation==='pivot_table'?'Colonne de pivot':operation==='groupby_aggregate'?'Variable à agréger':'Colonne'}<select value={column} onChange={e=>setColumn(e.target.value)}>{(operation==='clip_outliers_iqr'||operation==='groupby_aggregate'?numeric:columns).map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label>}
        {operation==='fill_missing'&&<><label>Stratégie<select value={strategy} onChange={e=>setStrategy(e.target.value)}><option value="median">Médiane</option><option value="mean">Moyenne</option><option value="mode">Mode</option><option value="constant">Valeur constante</option></select></label>{strategy==='constant'&&<label>Valeur constante<input value={constant} onChange={e=>setConstant(e.target.value)} placeholder="Valeur de remplacement"/></label>}</>}
        {operation==='rename_column'&&<label>Nouveau nom<input value={newName} onChange={e=>setNewName(e.target.value)} placeholder="nouveau_nom"/></label>}
        {operation==='cast_type'&&<label>Type cible<select value={dtype} onChange={e=>setDtype(e.target.value)}><option value="string">String</option><option value="integer">Integer</option><option value="float">Float</option><option value="boolean">Boolean</option><option value="datetime">Date/heure</option><option value="category">Catégorie</option></select></label>}
        {operation==='filter_rows'&&<><label>Opérateur<select value={operator} onChange={e=>setOperator(e.target.value)}><option value="eq">égal à</option><option value="ne">différent de</option><option value="gt">supérieur à</option><option value="gte">supérieur ou égal</option><option value="lt">inférieur à</option><option value="lte">inférieur ou égal</option><option value="contains">contient</option><option value="not_contains">ne contient pas</option><option value="is_null">est manquant</option><option value="not_null">n’est pas manquant</option></select></label>{!['is_null','not_null'].includes(operator)&&<label>Valeur<input value={filterValue} onChange={e=>setFilterValue(e.target.value)} placeholder="Valeur du filtre"/></label>}</>}
        {operation==='sort_rows'&&<div><span className="config-label">Ordre</span><div className="segmented"><button className={ascending?'active':''} onClick={()=>setAscending(true)}>Croissant</button><button className={!ascending?'active':''} onClick={()=>setAscending(false)}>Décroissant</button></div></div>}
        {operation==='clip_outliers_iqr'&&<><label>Facteur IQR<input type="number" min="0.1" step="0.1" value={iqrFactor} onChange={e=>setIqrFactor(Number(e.target.value)||1.5)}/></label><label>Action<select value={outlierMode} onChange={e=>setOutlierMode(e.target.value)}><option value="clip">Écrêter aux bornes</option><option value="remove">Supprimer les lignes</option></select></label></>}
        {['drop_columns','remove_duplicates','standardize','normalize_minmax','one_hot_encode'].includes(operation)&&<div><span className="config-label">{operation==='remove_duplicates'?'Sous-ensemble (vide = toutes les colonnes)':'Colonnes'}</span><VariableChecklist columns={operation==='standardize'||operation==='normalize_minmax'?numeric:operation==='one_hot_encode'?categorical:columns} selected={selected} setSelected={setSelected}/></div>}
        {operation==='add_calculated_column'&&<><label>Nom de la variable<input value={newName} onChange={e=>setNewName(e.target.value)} placeholder="indice_risque"/></label><label>Expression<input value={expression} onChange={e=>setExpression(e.target.value)} placeholder={'col("Age") * 0.5 + col("Score")'} /></label><small className="help-text">DSL sûre : col("Nom"), nombres, + − × ÷ ** %, abs(), sqrt(), log(), log1p(), round(). Aucun eval Python.</small></>}
        {operation==='groupby_aggregate'&&<><div><span className="config-label">Regrouper par</span><VariableChecklist columns={columns} selected={selected} setSelected={setSelected}/></div><label>Fonction<select value={aggFunction} onChange={e=>setAggFunction(e.target.value)}>{['mean','sum','min','max','median','count','nunique','std','var'].map(x=><option key={x}>{x}</option>)}</select></label><label>Alias optionnel<input value={aggAlias} onChange={e=>setAggAlias(e.target.value)} placeholder={`${column}_${aggFunction}`}/></label></>}
        {operation==='pivot_table'&&<><div><span className="config-label">Index</span><VariableChecklist columns={columns.filter((c:AnyObj)=>c.name!==column)} selected={selected} setSelected={setSelected}/></div><label>Valeur<select value={secondColumn} onChange={e=>setSecondColumn(e.target.value)}>{numeric.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><label>Agrégation<select value={pivotAgg} onChange={e=>setPivotAgg(e.target.value)}>{['mean','sum','min','max','median','count'].map(x=><option key={x}>{x}</option>)}</select></label></>}
        {operation==='melt_unpivot'&&<><div><span className="config-label">Colonnes identifiantes</span><VariableChecklist columns={columns} selected={selected} setSelected={setSelected}/></div><div><span className="config-label">Colonnes à dé-pivoter</span><VariableChecklist columns={columns.filter((c:AnyObj)=>!selected.includes(c.name))} selected={selected2} setSelected={setSelected2}/></div><label>Nom colonne variable<input value={varName} onChange={e=>setVarName(e.target.value)}/></label><label>Nom colonne valeur<input value={valueName} onChange={e=>setValueName(e.target.value)}/></label></>}
        {operation==='extract_date_parts'&&<div><span className="config-label">Composantes</span><div className="date-parts">{['year','quarter','month','day','weekday','hour'].map(p=><label key={p}><input type="checkbox" checked={dateParts.includes(p)} onChange={e=>setDateParts(e.target.checked?[...dateParts,p]:dateParts.filter(x=>x!==p))}/>{p}</label>)}</div></div>}
        <div className="prep-warning"><b>Transformation non destructive</b><span>Chaque action crée une version immuable; la source et les étapes restent auditables.</span></div>
        <RunButton busy={busy} label="Appliquer et créer une version" busyLabel="Transformation…" onClick={apply}/>
      </div></Panel>
    </div>

    <div className="two-col">
      <Panel title="Combiner avec un autre dataset"><div className="analysis-config prep-config"><label>Dataset secondaire<select value={otherDataset} onChange={e=>setOtherDataset(e.target.value)}><option value="">— sélectionner —</option>{catalog.map((d:AnyObj)=><option value={d.id} key={d.id}>{d.source_name??d.name} · v{d.version}</option>)}</select></label><label>Opération<select value={combineType} onChange={e=>setCombineType(e.target.value)}><option value="merge">Jointure par clé</option><option value="concat_rows">Concaténer les lignes</option><option value="concat_columns">Concaténer les colonnes</option></select></label>{combineType==='merge'&&<><label>Clé gauche<select value={leftKey||columns[0]?.name||''} onChange={e=>setLeftKey(e.target.value)}>{columns.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><label>Clé droite<select value={rightKey} onChange={e=>setRightKey(e.target.value)}>{otherColumns.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><label>Type<select value={joinHow} onChange={e=>setJoinHow(e.target.value)}><option value="inner">Inner</option><option value="left">Left</option><option value="right">Right</option><option value="outer">Outer</option></select></label></>}<RunButton busy={busy} label="Combiner et versionner" busyLabel="Combinaison…" onClick={combine}/><small className="help-text">La provenance du dataset secondaire est enregistrée dans l’opération.</small></div></Panel>
      <Panel title="Pipelines sauvegardés"><div className="pipeline-save"><input value={pipelineName} onChange={e=>setPipelineName(e.target.value)} placeholder="Nom du pipeline"/><button className="primary-btn" disabled={pipelineBusy==='save'} onClick={saveCurrentPipeline}>{pipelineBusy==='save'?'Enregistrement…':'Enregistrer la branche active'}</button></div><div className="saved-pipelines">{pipelines.length===0?<p className="quiet">Aucun pipeline enregistré.</p>:pipelines.map((p:AnyObj)=><div key={p.id}><div><b>{p.name}</b><small>{p.steps_count} étape(s) · {new Date(p.created_at).toLocaleString('fr-FR')}</small></div><button className="ghost-btn" disabled={pipelineBusy===p.id} onClick={()=>replayPipeline(p.id)}>{pipelineBusy===p.id?'Exécution…':'Rejouer depuis la source'}</button></div>)}</div></Panel>
    </div>

    <Panel title="Aperçu de la version active" action={<span className="quiet">v{result.dataset.version??1} · {result.preview.shown}/{result.preview.total}</span>}><DataTable preview={result.preview}/></Panel>
    <Panel title="Historique & rollback" action={<span className="quiet">{versions.length} version(s)</span>}><div className="version-timeline">{versions.map((v:AnyObj)=><div className={v.id===result.dataset.id?'version-row current':'version-row'} key={v.id}><span className="version-node">v{v.version}</span><div><b>{v.operation?.label??'Version du dataset'}</b><small>{v.name} · {v.created_at?new Date(v.created_at).toLocaleString('fr-FR'):'date inconnue'}</small></div>{v.id===result.dataset.id?<span className="current-chip">active</span>:<button className="ghost-btn" disabled={switching===v.id} onClick={()=>activate(v.id)}>{switching===v.id?'Ouverture…':'Réactiver'}</button>}</div>)}</div><p className="version-note">Réactiver une version antérieure ne supprime aucune version : une nouvelle transformation repart de cet état et crée une branche distincte.</p></Panel>
  </div>;
}

function VariableChecklist({ columns, selected, setSelected, numericOnly=false }: { columns: AnyObj[]; selected: string[]; setSelected:(v:string[])=>void; numericOnly?:boolean }) {
  const usable = numericOnly ? columns.filter(isNumeric) : columns;
  return <div className="check-grid">{usable.map(c=><label className={selected.includes(c.name)?'check-item selected':'check-item'} key={c.name}><input type="checkbox" checked={selected.includes(c.name)} onChange={e=>setSelected(e.target.checked?[...selected,c.name]:selected.filter(x=>x!==c.name))}/><span><b>{c.name}</b><small>{c.dtype}</small></span></label>)}</div>;
}

function RegressionView({ result, setError }: { result: AnyObj | null; setError:(s:string)=>void }) {
  const columns=result?.profile?.columns ?? []; const nums=columns.filter(isNumeric);
  const [dependent,setDependent]=useState(''); const [independents,setIndependents]=useState<string[]>([]); const [analysis,setAnalysis]=useState<AnyObj|null>(null); const [busy,setBusy]=useState(false);
  useEffect(()=>{ if(result){const dep=nums[nums.length-1]?.name??''; setDependent(dep); setIndependents(columns.filter((c:AnyObj)=>c.name!==dep).slice(0,2).map((c:AnyObj)=>c.name)); setAnalysis(null);} },[result?.dataset?.id]);
  if(!result) return <EmptyState title="Analyse de Régression" text="Chargez un dataset avant de configurer une régression linéaire."/>;
  async function run(){setBusy(true);setError('');try{setAnalysis(await runRegression(result!.dataset.id,{dependent,independents}));}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <div className="page"><div className="page-title"><div><span className="eyebrow">RÉGRESSION LINÉAIRE</span><h1>Analyse de Régression</h1><p>Choisissez une variable dépendante et une ou plusieurs variables explicatives. Le modèle retourne coefficients, intervalles de confiance et diagnostics de résidus.</p></div><span className="module-state implemented">implémenté</span></div>
    <Panel title="Configuration"><div className="analysis-config"><label>Variable dépendante<select value={dependent} onChange={e=>setDependent(e.target.value)}>{nums.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><div><span className="config-label">Variables explicatives</span><VariableChecklist columns={columns.filter((c:AnyObj)=>c.name!==dependent)} selected={independents} setSelected={setIndependents}/></div><RunButton busy={busy} label="Exécuter la régression" busyLabel="Calcul de la régression…" onClick={run}/></div></Panel>
    {analysis && <><div className="metrics six"><Stat label="N" value={analysis.n}/><Stat label="R²" value={formatNumber(analysis.r_squared,4)}/><Stat label="R² ajusté" value={formatNumber(analysis.adj_r_squared,4)}/><Stat label="RMSE" value={formatNumber(analysis.rmse)}/><Stat label="F" value={formatNumber(analysis.f_statistic)}/><Stat label="p modèle" value={pText(analysis.f_p_value)}/></div>
      <Panel title="Coefficients"><SimpleTable rows={analysis.coefficients} columns={[['term','Terme'],['estimate','Coefficient'],['std_error','Erreur-type'],['t','t'],['p_value','p-value'],['ci_low','IC 95% bas'],['ci_high','IC 95% haut']]}/></Panel>
      <div className="two-col"><Panel title="Tests statistiques"><div className="test-cards"><TestCard name="Shapiro-Wilk — résidus" stat={analysis.tests.shapiro_wilk_residuals.statistic} p={analysis.tests.shapiro_wilk_residuals.p_value} goodWhenHigh/><TestCard name="Breusch-Pagan" stat={analysis.tests.breusch_pagan.lm_statistic} p={analysis.tests.breusch_pagan.lm_p_value} goodWhenHigh/></div></Panel><Panel title="Résidus vs valeurs prédites"><ScatterPlot points={analysis.diagnostics.map((d:AnyObj)=>({x:d.predicted,y:d.residual}))} xLabel="Prédit" yLabel="Résidu" zeroLine/></Panel></div>
      <Panel title="Observé vs prédit"><ScatterPlot points={analysis.diagnostics.map((d:AnyObj)=>({x:d.predicted,y:d.observed}))} xLabel="Prédit" yLabel="Observé" diagonal/></Panel></>}
  </div>;
}

function AnovaView({ result, setError }: { result:AnyObj|null; setError:(s:string)=>void }) {
  const columns=result?.profile?.columns??[]; const nums=columns.filter(isNumeric);
  const [type,setType]=useState<'one'|'two'>('one'); const [response,setResponse]=useState(''); const [factor1,setFactor1]=useState(''); const [factor2,setFactor2]=useState(''); const [analysis,setAnalysis]=useState<AnyObj|null>(null); const [busy,setBusy]=useState(false);
  useEffect(()=>{if(result){setResponse(nums[0]?.name??''); const factors=columns.filter((c:AnyObj)=>c.name!==nums[0]?.name); setFactor1(factors[0]?.name??''); setFactor2(factors[1]?.name??''); setAnalysis(null);}},[result?.dataset?.id]);
  if(!result) return <EmptyState title="Analyse ANOVA" text="Chargez un dataset pour comparer les moyennes entre groupes."/>;
  async function run(){setBusy(true);setError('');try{setAnalysis(await runAnova(result!.dataset.id,{response,factor1,factor2:type==='two'?factor2:null}));}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <div className="page"><div className="page-title"><div><span className="eyebrow">ANALYSE DE VARIANCE</span><h1>Analyse ANOVA</h1><p>ANOVA à un ou deux facteurs, vérification des hypothèses, post-hoc de Tukey et distributions par groupe.</p></div><span className="module-state implemented">implémenté</span></div>
    <Panel title="Configuration"><div className="analysis-config"><div className="segmented"><button className={type==='one'?'active':''} onClick={()=>setType('one')}>ANOVA 1 facteur</button><button className={type==='two'?'active':''} onClick={()=>setType('two')}>ANOVA 2 facteurs</button></div><div className="form-row"><label>Variable réponse<select value={response} onChange={e=>setResponse(e.target.value)}>{nums.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><label>Facteur 1<select value={factor1} onChange={e=>setFactor1(e.target.value)}>{columns.filter((c:AnyObj)=>c.name!==response).map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label>{type==='two'&&<label>Facteur 2<select value={factor2} onChange={e=>setFactor2(e.target.value)}>{columns.filter((c:AnyObj)=>c.name!==response&&c.name!==factor1).map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label>}</div><RunButton busy={busy} label="Exécuter l’ANOVA" busyLabel="Calcul ANOVA…" onClick={run}/></div></Panel>
    {analysis && <><Panel title="Résultats de l’ANOVA"><SimpleTable rows={analysis.anova_table} columns={[['source','Source'],['sum_sq','Somme des carrés'],['df','ddl'],['f','F'],['p_value','p-value']]}/></Panel><div className="two-col"><Panel title="Conditions d’application"><div className="test-cards"><TestCard name="Levene — homogénéité" stat={analysis.levene.statistic} p={analysis.levene.p_value} goodWhenHigh/>{analysis.normality.map((x:AnyObj,i:number)=><TestCard key={i} name={`Shapiro-Wilk — ${x.group}`} stat={x.statistic} p={x.p_value} goodWhenHigh/>)}</div></Panel><Panel title="Statistiques descriptives par groupe"><SimpleTable rows={analysis.groups.map((g:AnyObj)=>({...g,boxplot:undefined}))} columns={Object.keys(analysis.groups[0]??{}).filter(k=>k!=='boxplot').map(k=>[k,k] as [string,string])}/></Panel></div>
      <Panel title="Boxplots par groupe"><GroupBoxplots groups={analysis.groups} factor1={analysis.factor1} factor2={analysis.factor2}/></Panel>{analysis.tukey?.length>0&&<Panel title="Test post-hoc de Tukey"><SimpleTable rows={analysis.tukey} columns={[['group1','Groupe 1'],['group2','Groupe 2'],['mean_diff','Différence'],['ci_low','IC bas'],['ci_high','IC haut'],['p_adj','p ajustée'],['reject','Significatif']]}/></Panel>}</>}
  </div>;
}

function PcaView({ result, setError }: { result:AnyObj|null; setError:(s:string)=>void }) {
  const nums=result?.profile?.columns?.filter(isNumeric)??[]; const [selected,setSelected]=useState<string[]>([]); const [scale,setScale]=useState(true); const [analysis,setAnalysis]=useState<AnyObj|null>(null); const [busy,setBusy]=useState(false);
  useEffect(()=>{if(result){setSelected(nums.slice(0,Math.min(5,nums.length)).map((c:AnyObj)=>c.name));setAnalysis(null);}},[result?.dataset?.id]);
  if(!result) return <EmptyState title="Analyse en Composantes Principales" text="Chargez un dataset comportant au moins deux variables numériques."/>;
  async function run(){setBusy(true);setError('');try{setAnalysis(await runPca(result!.dataset.id,{columns:selected,scale}));}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <div className="page"><div className="page-title"><div><span className="eyebrow">ANALYSE MULTIVARIÉE</span><h1>Analyse en Composantes Principales</h1><p>Adéquation, variance expliquée, contributions des variables, projection des individus et matrice de covariance.</p></div><span className="module-state implemented">implémenté</span></div>
    <Panel title="Variables de l’ACP"><div className="analysis-config"><VariableChecklist columns={nums} selected={selected} setSelected={setSelected} numericOnly/><label className="switch-line"><input type="checkbox" checked={scale} onChange={e=>setScale(e.target.checked)}/> Standardiser les variables avant l’ACP</label><RunButton busy={busy} label="Lancer l’ACP" busyLabel="Calcul ACP…" onClick={run}/></div></Panel>
    {analysis&&<><div className="metrics"><Stat label="KMO" value={formatNumber(analysis.adequacy.kmo,4)}/><Stat label="Bartlett χ²" value={formatNumber(analysis.adequacy.bartlett_chi2)}/><Stat label="p Bartlett" value={pText(analysis.adequacy.bartlett_p_value)}/><Stat label="Variance PC1+PC2" value={`${formatNumber((analysis.variance[0]?.explained_pct??0)+(analysis.variance[1]?.explained_pct??0),2)} %`}/></div><div className="two-col"><Panel title="Scree plot"><BarChart rows={analysis.variance} valueKey="explained_pct" labelKey="component" suffix="%"/></Panel><Panel title="Projection des individus — PC1 / PC2"><ScatterPlot points={analysis.scores.map((p:AnyObj)=>({x:p.PC1,y:p.PC2}))} xLabel="PC1" yLabel="PC2"/></Panel></div><Panel title="Variance expliquée"><SimpleTable rows={analysis.variance} columns={[['component','Composante'],['eigenvalue','Valeur propre'],['explained_pct','Variance %'],['cumulative_pct','Cumul %']]}/></Panel><div className="two-col"><Panel title="Cercle / charges factorielles"><LoadingPlot rows={analysis.variables}/></Panel><Panel title="Contributions des variables — PC1"><BarChart rows={analysis.variables} valueKey="contrib_PC1" labelKey="variable" suffix="%"/></Panel></div><Panel title="Matrice des composantes principales"><SimpleTable rows={analysis.variables} columns={Object.keys(analysis.variables[0]??{}).filter(k=>k==='variable'||(/^PC\d+$/.test(k))).map(k=>[k,k] as [string,string])}/></Panel><Panel title="Matrice de covariance"><SimpleTable rows={analysis.covariance} columns={Object.keys(analysis.covariance[0]??{}).map(k=>[k,k] as [string,string])}/></Panel></>}
  </div>;
}

function ClusterView({ result, setError }: { result:AnyObj|null; setError:(s:string)=>void }) {
  const nums=result?.profile?.columns?.filter(isNumeric)??[]; const [selected,setSelected]=useState<string[]>([]); const [k,setK]=useState(3); const [analysis,setAnalysis]=useState<AnyObj|null>(null); const [busy,setBusy]=useState(false);
  useEffect(()=>{if(result){setSelected(nums.slice(0,Math.min(5,nums.length)).map((c:AnyObj)=>c.name));setAnalysis(null);}},[result?.dataset?.id]);
  if(!result) return <EmptyState title="Clustering K-means" text="Chargez un dataset avec au moins deux variables numériques."/>;
  async function run(){setBusy(true);setError('');try{setAnalysis(await runClustering(result!.dataset.id,{columns:selected,k}));}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <div className="page"><div className="page-title"><div><span className="eyebrow">CLUSTERING NON SUPERVISÉ</span><h1>Clustering K-means</h1><p>Regroupez les observations, mesurez la qualité du partitionnement et caractérisez chaque cluster.</p></div><span className="module-state implemented">implémenté</span></div>
    <Panel title="Configuration"><div className="analysis-config"><VariableChecklist columns={nums} selected={selected} setSelected={setSelected} numericOnly/><label>Nombre de clusters K<input className="number-input" type="number" min={2} max={10} value={k} onChange={e=>setK(Math.max(2,Math.min(10,Number(e.target.value)||2)))}/></label><RunButton busy={busy} label="Lancer le clustering" busyLabel="Calcul des clusters…" onClick={run}/></div></Panel>
    {analysis&&<><div className="metrics"><Stat label="K" value={analysis.k}/><Stat label="Silhouette" value={formatNumber(analysis.silhouette,4)}/><Stat label="Inertie" value={formatNumber(analysis.inertia)}/><Stat label="Variance PCA 2D" value={`${formatNumber(analysis.pca_explained_pct,2)} %`}/></div><div className="two-col"><Panel title="Clusters identifiés"><ClusterScatter points={analysis.points}/></Panel><Panel title="Comparaison du nombre de clusters"><LineChart rows={analysis.comparison} xKey="k" yKey="silhouette"/></Panel></div><Panel title="Profils des clusters"><SimpleTable rows={analysis.profiles} columns={Object.keys(analysis.profiles[0]??{}).map(k=>[k,k] as [string,string])}/></Panel><Panel title="Centres des clusters"><SimpleTable rows={analysis.centers} columns={Object.keys(analysis.centers[0]??{}).map(k=>[k,k] as [string,string])}/></Panel></>}
  </div>;
}

function TestCard({ name, stat, p, goodWhenHigh=false }: { name:string; stat:any; p:any; goodWhenHigh?:boolean }) { const ok=typeof p==='number' ? (goodWhenHigh?p>=0.05:p<0.05) : false; return <div className="test-card"><div><b>{name}</b><small>Statistique {formatNumber(stat)}</small></div><span className={ok?'test-ok':'test-warn'}>p {pText(p)}</span></div>; }
function SimpleTable({ rows, columns }: { rows:AnyObj[]; columns:[string,string][] }) { if(!rows?.length)return <div className="quiet-empty">Aucun résultat tabulaire.</div>; return <div className="table-scroll compact"><table><thead><tr>{columns.map(([k,l])=><th key={k}>{l}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={i}>{columns.map(([k])=><td key={k}>{typeof r[k]==='boolean'?(r[k]?'Oui':'Non'):formatNumber(r[k])}</td>)}</tr>)}</tbody></table></div>; }
function ScatterPlot({ points, xLabel, yLabel, zeroLine=false, diagonal=false }: { points:{x:number,y:number,cluster?:number}[]; xLabel:string; yLabel:string; zeroLine?:boolean; diagonal?:boolean }) { const clean=points.filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)); if(!clean.length)return <div className="quiet-empty">Aucun point.</div>; const xs=clean.map(p=>p.x),ys=clean.map(p=>p.y),xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys),sx=(x:number)=>40+(x-xmin)/Math.max(xmax-xmin,1e-9)*520,sy=(y:number)=>235-(y-ymin)/Math.max(ymax-ymin,1e-9)*190; return <div className="svg-chart"><svg viewBox="0 0 600 280" role="img"><line x1="40" y1="235" x2="560" y2="235" className="axis"/><line x1="40" y1="45" x2="40" y2="235" className="axis"/>{zeroLine&&ymin<=0&&ymax>=0&&<line x1="40" y1={sy(0)} x2="560" y2={sy(0)} className="guide"/>}{diagonal&&<line x1={sx(Math.max(xmin,ymin))} y1={sy(Math.max(xmin,ymin))} x2={sx(Math.min(xmax,ymax))} y2={sy(Math.min(xmax,ymax))} className="diag"/>}{clean.map((p,i)=><circle key={i} cx={sx(p.x)} cy={sy(p.y)} r="2.5" className="dot"/>)}<text x="300" y="270" className="axis-label">{xLabel}</text><text x="12" y="145" className="axis-label" transform="rotate(-90 12 145)">{yLabel}</text></svg></div>; }
function ClusterScatter({ points }: { points:AnyObj[] }) { const clean=points.filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)); if(!clean.length)return <div className="quiet-empty">Aucun point.</div>; const xs=clean.map(p=>p.x),ys=clean.map(p=>p.y),xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys),sx=(x:number)=>35+(x-xmin)/Math.max(xmax-xmin,1e-9)*530,sy=(y:number)=>235-(y-ymin)/Math.max(ymax-ymin,1e-9)*195; return <div className="svg-chart"><svg viewBox="0 0 600 270"><line x1="35" y1="235" x2="565" y2="235" className="axis"/><line x1="35" y1="40" x2="35" y2="235" className="axis"/>{clean.map((p,i)=><circle key={i} cx={sx(p.x)} cy={sy(p.y)} r="3" className={`cluster-dot c${p.cluster%6}`}/>)}</svg><div className="cluster-legend">{[...new Set(clean.map(p=>p.cluster))].map(c=><span key={c}><i className={`cluster-dot c${c%6}`}/>Cluster {c}</span>)}</div></div>; }
function BarChart({ rows, valueKey, labelKey, suffix='' }: { rows:AnyObj[]; valueKey:string; labelKey:string; suffix?:string }) { const vals=rows.map(r=>Number(r[valueKey])||0),max=Math.max(1,...vals); return <div className="bar-chart">{rows.map((r,i)=><div className="bar-row" key={i}><span title={String(r[labelKey])}>{String(r[labelKey])}</span><div><i style={{width:`${Math.max(1,(Number(r[valueKey])||0)/max*100)}%`}}/></div><b>{formatNumber(r[valueKey],2)}{suffix}</b></div>)}</div>; }
function LineChart({ rows, xKey, yKey }: { rows:AnyObj[]; xKey:string; yKey:string }) { if(!rows?.length)return <div className="quiet-empty">Aucun point.</div>; const xs=rows.map(r=>Number(r[xKey])),ys=rows.map(r=>Number(r[yKey])),xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys),sx=(x:number)=>45+(x-xmin)/Math.max(xmax-xmin,1)*500,sy=(y:number)=>220-(y-ymin)/Math.max(ymax-ymin,1e-9)*160; const pts=rows.map(r=>`${sx(Number(r[xKey]))},${sy(Number(r[yKey]))}`).join(' '); return <div className="svg-chart"><svg viewBox="0 0 600 260"><line x1="45" y1="220" x2="545" y2="220" className="axis"/><line x1="45" y1="60" x2="45" y2="220" className="axis"/><polyline points={pts} className="trend"/>{rows.map((r,i)=><g key={i}><circle cx={sx(Number(r[xKey]))} cy={sy(Number(r[yKey]))} r="4" className="trend-dot"/><text x={sx(Number(r[xKey]))} y="240" className="tick">{r[xKey]}</text></g>)}</svg></div>; }
function LoadingPlot({ rows }: { rows:AnyObj[] }) { const pts=rows.filter(r=>Number.isFinite(r.PC1)&&Number.isFinite(r.PC2)); const max=Math.max(1,...pts.flatMap(r=>[Math.abs(r.PC1),Math.abs(r.PC2)])); const s=(v:number)=>300+v/max*190; const sy=(v:number)=>140-v/max*95; return <div className="svg-chart"><svg viewBox="0 0 600 280"><circle cx="300" cy="140" r="95" className="circle-guide"/><line x1="110" y1="140" x2="490" y2="140" className="guide"/><line x1="300" y1="35" x2="300" y2="245" className="guide"/>{pts.map((r,i)=><g key={i}><line x1="300" y1="140" x2={s(r.PC1)} y2={sy(r.PC2)} className="loading-line"/><circle cx={s(r.PC1)} cy={sy(r.PC2)} r="3" className="loading-dot"/><text x={s(r.PC1)+4} y={sy(r.PC2)-4} className="loading-label">{r.variable}</text></g>)}</svg></div>; }
function GroupBoxplots({ groups, factor1, factor2 }: { groups:AnyObj[]; factor1:string; factor2?:string|null }) { if(!groups.length)return <div className="quiet-empty">Aucun groupe.</div>; const vals=groups.flatMap(g=>[g.boxplot?.min,g.boxplot?.max]).filter(Number.isFinite),min=Math.min(...vals),max=Math.max(...vals),span=Math.max(max-min,1e-9),y=(v:number)=>215-(v-min)/span*155; return <div className="svg-chart tall"><svg viewBox="0 0 720 285"><line x1="45" y1="215" x2="690" y2="215" className="axis"/><line x1="45" y1="60" x2="45" y2="215" className="axis"/>{groups.map((g,i)=>{const x=75+i*(590/Math.max(groups.length,1)),b=g.boxplot,label=factor2?`${g[factor1]}·${g[factor2]}`:String(g[factor1]);return <g key={i}><line x1={x} x2={x} y1={y(b.whisker_high)} y2={y(b.whisker_low)} className="box-whisker"/><rect x={x-16} y={y(b.q3)} width="32" height={Math.max(2,y(b.q1)-y(b.q3))} className="box-svg"/><line x1={x-16} x2={x+16} y1={y(b.median)} y2={y(b.median)} className="median-svg"/><text x={x} y="238" className="tick" transform={`rotate(25 ${x} 238)`}>{label}</text></g>})}</svg></div>; }


function StatisticalLab({ result, setError }: { result:AnyObj|null; setError:(s:string)=>void }) {
  const cols=result?.profile?.columns??[]; const nums=cols.filter(isNumeric); const cats=cols.filter((c:AnyObj)=>!isNumeric(c));
  const [value,setValue]=useState(''); const [group,setGroup]=useState(''); const [x,setX]=useState(''); const [y,setY]=useState('');
  const [test,setTest]=useState('welch_t'); const [advice,setAdvice]=useState<AnyObj|null>(null); const [testResult,setTestResult]=useState<AnyObj|null>(null);
  const [corrCols,setCorrCols]=useState<string[]>([]); const [corrMethod,setCorrMethod]=useState<'pearson'|'spearman'>('pearson'); const [corr,setCorr]=useState<AnyObj|null>(null); const [busy,setBusy]=useState('');
  useEffect(()=>{if(result){setValue(nums[0]?.name??'');setGroup(cats[0]?.name??cols[1]?.name??'');setX(nums[0]?.name??cols[0]?.name??'');setY(nums[1]?.name??cols[1]?.name??'');setCorrCols(nums.slice(0,Math.min(8,nums.length)).map((c:AnyObj)=>c.name));setAdvice(null);setTestResult(null);setCorr(null);}},[result?.dataset?.id]);
  if(!result) return <EmptyState title="Tests statistiques" text="Chargez un dataset pour accéder au moteur de tests et au Statistical Test Advisor."/>;
  async function advise(){setBusy('advice');setError('');try{const a=await getTestAdvice(result!.dataset.id,{value,group});setAdvice(a);setTest(a.recommended);}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy('');}}
  async function runTest(){setBusy('test');setError('');try{let payload:AnyObj={test};if(['pearson','spearman','chi_square','fisher','paired_t','wilcoxon'].includes(test))payload={...payload,x,y,paired:['paired_t','wilcoxon'].includes(test)};else payload={...payload,value,group};setTestResult(await runStatisticalTest(result!.dataset.id,payload));}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy('');}}
  async function runCorr(){setBusy('corr');setError('');try{setCorr(await runCorrelations(result!.dataset.id,{columns:corrCols,method:corrMethod}));}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy('');}}
  const testOptions=[['student_t','t de Student'],['welch_t','t de Welch'],['mann_whitney','Mann-Whitney'],['anova_oneway','ANOVA 1 facteur'],['kruskal_wallis','Kruskal-Wallis'],['pearson','Corrélation de Pearson'],['spearman','Corrélation de Spearman'],['chi_square','Chi-deux'],['fisher','Fisher exact 2×2'],['paired_t','t apparié'],['wilcoxon','Wilcoxon apparié']];
  return <div className="page"><div className="page-title"><div><span className="eyebrow">STATISTICAL ENGINE</span><h1>Tests statistiques & corrélations</h1><p>Tests paramétriques/non paramétriques avec diagnostic des hypothèses et recommandation déterministe.</p></div><span className="module-state implemented">implémenté</span></div>
    <div className="two-col"><Panel title="Statistical Test Advisor"><div className="analysis-config"><label>Mesure numérique<select value={value} onChange={e=>setValue(e.target.value)}>{nums.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><label>Variable de groupe<select value={group} onChange={e=>setGroup(e.target.value)}>{cols.filter((c:AnyObj)=>c.name!==value).map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><RunButton busy={busy==='advice'} label="Recommander un test" busyLabel="Diagnostic…" onClick={advise}/>{advice&&<div className="advisor-box"><span>TEST RECOMMANDÉ</span><b>{advice.recommended}</b><p>{advice.reason}</p><small>La recommandation est calculée à partir des types, effectifs, Shapiro-Wilk et Levene.</small></div>}</div></Panel>
      <Panel title="Exécuter un test"><div className="analysis-config"><label>Test<select value={test} onChange={e=>setTest(e.target.value)}>{testOptions.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>{['pearson','spearman','chi_square','fisher','paired_t','wilcoxon'].includes(test)?<div className="form-row"><label>Variable X<select value={x} onChange={e=>setX(e.target.value)}>{cols.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><label>Variable Y<select value={y} onChange={e=>setY(e.target.value)}>{cols.filter((c:AnyObj)=>c.name!==x).map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label></div>:<div className="form-row"><label>Mesure<select value={value} onChange={e=>setValue(e.target.value)}>{nums.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><label>Groupe<select value={group} onChange={e=>setGroup(e.target.value)}>{cols.filter((c:AnyObj)=>c.name!==value).map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label></div>}<RunButton busy={busy==='test'} label="Exécuter le test" busyLabel="Calcul…" onClick={runTest}/></div></Panel></div>
    {testResult&&<Panel title="Résultat du test"><div className="metrics"><Stat label="Test" value={testResult.test}/><Stat label="Statistique" value={formatNumber(testResult.statistic,4)}/><Stat label="p-value" value={pText(testResult.p_value)}/><Stat label="Décision α=0,05" value={testResult.significant?'Significatif':'Non significatif'}/></div>{testResult.diagnostics?.levene&&<div className="test-cards"><TestCard name="Levene" stat={testResult.diagnostics.levene.statistic} p={testResult.diagnostics.levene.p_value} goodWhenHigh/>{(testResult.diagnostics.normality??[]).map((n:AnyObj,i:number)=><TestCard key={i} name={`Shapiro — ${n.group}`} stat={n.statistic} p={n.p_value} goodWhenHigh/>)}</div>}{testResult.contingency&&<SimpleTable rows={testResult.contingency} columns={Object.keys(testResult.contingency[0]??{}).map(k=>[k,k] as [string,string])}/>}</Panel>}
    <Panel title="Matrice de corrélation"><div className="analysis-config"><VariableChecklist columns={nums} selected={corrCols} setSelected={setCorrCols} numericOnly/><div className="form-row"><label>Méthode<select value={corrMethod} onChange={e=>setCorrMethod(e.target.value as 'pearson'|'spearman')}><option value="pearson">Pearson</option><option value="spearman">Spearman</option></select></label><RunButton busy={busy==='corr'} label="Calculer la matrice" busyLabel="Calcul…" onClick={runCorr}/></div></div>{corr&&<><SimpleTable rows={corr.matrix} columns={['variable',...corr.columns].map(k=>[k,k] as [string,string])}/><h4 className="subheading">Relations les plus fortes</h4><SimpleTable rows={corr.pairs.slice(0,15)} columns={[['x','X'],['y','Y'],['coefficient','Coefficient'],['p_value','p-value'],['n','n']]}/></>}</Panel>
  </div>;
}

function VisualizationStudio({ result, setError }: { result:AnyObj|null; setError:(s:string)=>void }) {
  const cols=result?.profile?.columns??[]; const [chartType,setChartType]=useState('auto'); const [x,setX]=useState(''); const [y,setY]=useState(''); const [aggregation,setAggregation]=useState('none'); const [viz,setViz]=useState<AnyObj|null>(null); const [recs,setRecs]=useState<AnyObj[]>([]); const [busy,setBusy]=useState(false);
  useEffect(()=>{if(result){setX(cols[0]?.name??'');setY(cols[1]?.name??'');setViz(null);setRecs([]);}},[result?.dataset?.id]);
  if(!result) return <EmptyState title="Visualization Studio" text="Chargez un dataset pour concevoir des visualisations interactives."/>;
  async function build(){setBusy(true);setError('');try{setViz(await buildVisualization(result!.dataset.id,{chart_type:chartType,x,y:y||null,aggregation,bins:20}));}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  async function recommend(){setBusy(true);setError('');try{const r=await recommendVisualizations(result!.dataset.id,[x,y].filter(Boolean));setRecs(r.recommendations??[]);}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  function applyRec(r:AnyObj){setChartType(r.type);setX(r.x??x);setY(r.y??'');setAggregation(r.aggregation??'none');}
  return <div className="page"><div className="page-title"><div><span className="eyebrow">VISUALIZATION STUDIO</span><h1>Visualisation intelligente</h1><p>Construisez des graphiques à partir de résultats réellement agrégés par le backend.</p></div><span className="module-state implemented">implémenté</span></div>
    <div className="viz-layout"><Panel title="Configuration"><div className="analysis-config"><label>Type<select value={chartType} onChange={e=>setChartType(e.target.value)}><option value="auto">Auto</option><option value="histogram">Histogramme</option><option value="scatter">Nuage de points</option><option value="box">Boxplot</option><option value="bar">Barres</option><option value="line">Courbe</option></select></label><label>Axe X<select value={x} onChange={e=>setX(e.target.value)}>{cols.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><label>Axe Y<select value={y} onChange={e=>setY(e.target.value)}><option value="">— aucun —</option>{cols.filter((c:AnyObj)=>c.name!==x).map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><label>Agrégation<select value={aggregation} onChange={e=>setAggregation(e.target.value)}><option value="none">Aucune</option><option value="count">Count</option><option value="mean">Moyenne</option><option value="sum">Somme</option><option value="median">Médiane</option><option value="min">Minimum</option><option value="max">Maximum</option></select></label><div className="button-row"><RunButton busy={busy} label="Générer" busyLabel="Calcul…" onClick={build}/><button className="secondary-btn" disabled={busy} onClick={recommend}>✦ Recommander</button></div></div></Panel>
      <Panel title="Smart Visualization"><div className="recommendation-list">{recs.length?recs.map((r,i)=><button key={i} onClick={()=>applyRec(r)}><b>{r.type}</b><span>{r.reason}</span><small>{[r.x,r.y].filter(Boolean).join(' × ')}</small></button>):<div className="quiet-empty">Cliquez sur « Recommander » pour obtenir des choix adaptés aux variables.</div>}</div></Panel></div>
    <Panel title={viz?.title??'Aperçu du graphique'}>{!viz?<div className="viz-placeholder">Sélectionnez vos variables puis générez le graphique.</div>:<VizRenderer viz={viz}/>}</Panel>
  </div>;
}

function VizRenderer({viz}:{viz:AnyObj}) {
  if(viz.type==='histogram') return <Histogram bins={viz.data}/>;
  if(viz.type==='scatter') return <ScatterPlot points={viz.data} xLabel={viz.x} yLabel={viz.y}/>;
  if(viz.type==='box') return <GroupBoxplots groups={viz.data.map((d:AnyObj)=>({...d,boxplot:d,group:d.group}))} factor1="group"/>;
  if(viz.type==='bar'||viz.type==='line') return <BarChart rows={viz.data} valueKey="value" labelKey="label"/>;
  return <pre className="result-json">{JSON.stringify(viz,null,2)}</pre>;
}

function SqlWorkspace({ result, setError }: { result:AnyObj|null; setError:(s:string)=>void }) {
  const [sql,setSql]=useState('SELECT * FROM dataset LIMIT 25'); const [out,setOut]=useState<AnyObj|null>(null); const [info,setInfo]=useState<AnyObj|null>(null); const [busy,setBusy]=useState(false);
  useEffect(()=>{if(!result)return;setOut(null);getEngineInfo(result.dataset.id).then(setInfo).catch(e=>setError(e instanceof Error?e.message:String(e)));},[result?.dataset?.id]);
  if(!result) return <EmptyState title="SQL Workspace" text="Chargez un dataset. Il sera exposé en lecture seule sous le nom de table dataset."/>;
  async function execute(){setBusy(true);setError('');try{setOut(await runSql(result!.dataset.id,sql,500));}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <div className="page"><div className="page-title"><div><span className="eyebrow">DUCKDB / LOCAL SQL</span><h1>SQL Workspace</h1><p>Interrogez le dataset actif avec une couche SQL locale en lecture seule.</p></div><span className="module-state implemented">implémenté</span></div>
    {info&&<div className="metrics"><Stat label="Moteur actif" value={info.preferred_engine}/><Stat label="DuckDB" value={info.engines.duckdb??'fallback'}/><Stat label="Polars" value={info.engines.polars??'fallback'}/><Stat label="Taille estimée" value={`${formatNumber(info.dataset.estimated_size_bytes/1024)} Ko`}/></div>}
    <div className="sql-layout"><Panel title="Éditeur SQL" action={<span className="read-only-chip">READ ONLY</span>}><textarea className="sql-editor" value={sql} onChange={e=>setSql(e.target.value)} spellCheck={false}/><div className="button-row"><RunButton busy={busy} label="Exécuter" busyLabel="Exécution…" onClick={execute}/><small className="help-text">Table disponible : <code>dataset</code> · SELECT/CTE uniquement</small></div></Panel><Panel title="Schéma"><div className="schema-list">{result.profile.columns.map((c:AnyObj)=><div key={c.name}><b>{c.name}</b><span>{c.dtype}</span></div>)}</div></Panel></div>
    {out&&<Panel title="Résultats" action={<span className="quiet">{out.returned_rows} lignes · {formatNumber(out.elapsed_ms)} ms · {out.engine}</span>}><DataTable preview={{columns:out.columns,rows:out.rows,shown:out.returned_rows,total:out.returned_rows}}/>{out.truncated&&<div className="warning-box">Résultat tronqué à {out.limit} lignes.</div>}</Panel>}
  </div>;
}

function ModelView({ result, target, setTarget, algorithm, setAlgorithm, training, automlRunning, doTrain, doAutoML, model }: { result: AnyObj | null; target: string; setTarget:(v:string)=>void; algorithm:string; setAlgorithm:(v:string)=>void; training:boolean; automlRunning:boolean; doTrain:()=>void; doAutoML:(c:{primary_metric:string;cv_folds:number;tune:boolean;max_candidates:number})=>void; model:AnyObj|null }) {
  const [metric,setMetric]=useState('auto'); const [folds,setFolds]=useState(5); const [tune,setTune]=useState(true); const [maxCandidates,setMaxCandidates]=useState(5);
  if (!result) return <EmptyState title="Modélisation" text="Chargez un dataset avant de sélectionner une cible et d’entraîner un modèle."/>;
  const benchmark=model?.benchmark??[]; const importance=model?.feature_importance??[]; const guardrails=model?.guardrails??[];
  return <div className="page"><div className="page-title"><div><span className="eyebrow">MACHINE LEARNING · AUTOML</span><h1>Modélisation professionnelle</h1><p>Benchmark multi-modèles, validation croisée, train/validation/test, tuning contrôlé, garde-fous et Model Card.</p></div><span className="module-state implemented">v0.9 compatible</span></div>
    <div className="two-col model-layout"><Panel title="AutoML"><div className="stack-form"><label>Variable cible<select value={target} onChange={e=>setTarget(e.target.value)}>{result.profile.columns.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><div className="form-row"><label>Métrique principale<select value={metric} onChange={e=>setMetric(e.target.value)}><option value="auto">Auto</option><option value="roc_auc">ROC-AUC</option><option value="f1_weighted">F1 pondéré</option><option value="balanced_accuracy">Balanced accuracy</option><option value="accuracy">Accuracy</option><option value="rmse">RMSE</option><option value="mae">MAE</option><option value="r2">R²</option></select></label><label>CV<input type="number" min={2} max={10} value={folds} onChange={e=>setFolds(Number(e.target.value))}/></label><label>Candidats<input type="number" min={2} max={6} value={maxCandidates} onChange={e=>setMaxCandidates(Number(e.target.value))}/></label></div><label className="switch-line"><input type="checkbox" checked={tune} onChange={e=>setTune(e.target.checked)}/> Optimisation contrôlée des hyperparamètres</label><button className="primary-btn real-button" disabled={automlRunning} onClick={()=>doAutoML({primary_metric:metric,cv_folds:folds,tune,max_candidates:maxCandidates})}>{automlRunning?'AutoML en cours…':'▶ Lancer AutoML'}</button><small className="help-text">Le jeu de test final reste isolé jusqu’à l’évaluation du modèle sélectionné.</small></div></Panel>
      <Panel title="Entraînement manuel"><div className="stack-form"><label>Algorithme<select value={algorithm} onChange={e=>setAlgorithm(e.target.value)}><option value="auto">Auto baseline</option><option value="linear_regression">Régression linéaire</option><option value="ridge">Ridge</option><option value="logistic_regression">Régression logistique</option><option value="random_forest">Random Forest</option><option value="extra_trees">Extra Trees</option><option value="gradient_boosting">Gradient Boosting</option><option value="hist_gradient_boosting">Histogram Gradient Boosting</option></select></label><button className="secondary-btn real-button" disabled={training} onClick={doTrain}>{training?'Entraînement…':'Entraîner un modèle précis'}</button><ul className="guardrails compact"><li>✓ Imputation + encodage dans le pipeline</li><li>✓ Split reproductible 60/20/20</li><li>✓ Test final non utilisé pour l’optimisation</li><li>✓ Modèle et Model Card sauvegardés localement</li></ul></div></Panel></div>
    {model&&<><div className="metrics six"><Stat label="Tâche" value={model.task}/><Stat label="Algorithme retenu" value={model.algorithm}/><Stat label="Train" value={model.rows_train}/><Stat label="Validation" value={model.rows_validation??'—'}/><Stat label="Test final" value={model.rows_test}/><Stat label="Métrique" value={model.primary_metric??model.model_card?.primary_metric??'auto'}/></div>
      <Panel title="Métriques — test final" action={<code>{model.model_id?.slice(0,8)}…</code>}><div className="metric-results">{Object.entries(model.metrics??{}).map(([k,v])=><span key={k}><small>{k}</small><b>{formatNumber(v)}</b></span>)}</div>{model.validation_metrics&&<div className="validation-line"><b>Validation avant test final :</b>{Object.entries(model.validation_metrics).map(([k,v])=><span key={k}>{k}: {formatNumber(v)}</span>)}</div>}</Panel>
      {benchmark.length>0&&<Panel title="Benchmark AutoML"><SimpleTable rows={benchmark} columns={[["label","Modèle"],["validation_score","Score validation"],["cv_mean","Moyenne CV"],["cv_std","Écart-type CV"],["cv_folds","Folds"]]}/></Panel>}
      <div className="two-col"><Panel title="Garde-fous ML">{guardrails.length?<div className="ml-guardrail-list">{guardrails.map((g:AnyObj,i:number)=><div key={i} className={`ml-guardrail ${g.severity}`}><b>{g.code}</b><span>{g.message}</span>{g.columns&&<small>{JSON.stringify(g.columns)}</small>}</div>)}</div>:<div className="quiet-empty">Aucun diagnostic disponible.</div>}</Panel><Panel title="Importance des variables — permutation">{importance.length?<BarChart rows={importance.slice(0,12).map((x:AnyObj)=>({...x,importance_abs:Math.abs(Number(x.importance)||0)}))} valueKey="importance_abs" labelKey="feature"/>:<div className="quiet-empty">Importance indisponible pour ce modèle.</div>}</Panel></div>
      {model.best_params&&Object.keys(model.best_params).length>0&&<Panel title="Hyperparamètres retenus"><pre className="result-json">{JSON.stringify(model.best_params,null,2)}</pre></Panel>}
      {model.model_card&&<Panel title="Model Card"><div className="model-card-grid"><div><span>Cible</span><b>{model.model_card.target}</b></div><div><span>Dataset</span><b>{model.model_card.dataset?.name??'—'} · v{model.model_card.dataset?.version??'—'}</b></div><div><span>Validation</span><b>{model.model_card.validation_strategy?.split}</b></div><div><span>Créé</span><b>{new Date(model.model_card.created_at).toLocaleString('fr-FR')}</b></div></div><div className="limitation-box"><b>Limites connues</b><ul>{(model.model_card.known_limitations??[]).map((x:string)=><li key={x}>{x}</li>)}</ul></div><code className="model-id">Model ID: {model.model_id}</code></Panel>}
    </>}
  </div>;
}
function PredictView({ model, text, setText, predicting, doPredict, prediction }: { model:AnyObj|null; text:string; setText:(v:string)=>void; predicting:boolean; doPredict:()=>void; prediction:AnyObj|null }) { if(!model)return <EmptyState title="Prédictions" text="Entraînez d’abord un modèle dans l’onglet Modélisation."/>; return <div className="page"><div className="page-title"><div><span className="eyebrow">INFERENCE</span><h1>Prédictions</h1><p>Soumettez de nouvelles observations au pipeline entraîné.</p></div></div><Panel title="Observations à prédire" action={<code>{model.model_id.slice(0,8)}…</code>}><textarea className="json-editor" value={text} onChange={e=>setText(e.target.value)} spellCheck={false}/><button className="primary-btn real-button" disabled={predicting} onClick={doPredict}>{predicting?'Prédiction…':'▶ Lancer la prédiction'}</button></Panel>{prediction&&<Panel title="Résultat"><pre className="result-json">{JSON.stringify(prediction,null,2)}</pre></Panel>}</div>; }

function ForecastView({ result, setError }: { result:AnyObj|null; setError:(s:string)=>void }) {
  const cols=result?.profile?.columns??[]; const numeric=cols.filter(isNumeric);
  const [dateColumn,setDateColumn]=useState(''); const [targetCol,setTargetCol]=useState(''); const [horizon,setHorizon]=useState(12); const [frequency,setFrequency]=useState('auto'); const [method,setMethod]=useState('auto'); const [out,setOut]=useState<AnyObj|null>(null); const [busy,setBusy]=useState(false);
  useEffect(()=>{if(!result)return; const dateGuess=cols.find((c:AnyObj)=>/date|time|timestamp|annee|year|mois|month/i.test(c.name))?.name??cols[0]?.name??''; setDateColumn(dateGuess);setTargetCol(numeric[0]?.name??'');setOut(null);},[result?.dataset?.id]);
  if(!result) return <EmptyState title="Forecasting" text="Chargez une série temporelle pour comparer plusieurs méthodes et produire une prévision."/>;
  async function run(){if(!dateColumn||!targetCol)return;setBusy(true);setError('');try{setOut(await runForecast(result!.dataset.id,{date_column:dateColumn,target:targetCol,horizon,frequency,method}));}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <div className="page"><div className="page-title"><div><span className="eyebrow">TIME SERIES</span><h1>Forecasting</h1><p>Comparaison de méthodes sur une fenêtre de validation, puis prévision avec intervalle empirique à 95 %.</p></div><span className="module-state implemented">implémenté</span></div>
    <Panel title="Configuration"><div className="analysis-config"><div className="form-row"><label>Date<select value={dateColumn} onChange={e=>setDateColumn(e.target.value)}>{cols.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><label>Variable cible<select value={targetCol} onChange={e=>setTargetCol(e.target.value)}>{numeric.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label><label>Horizon<input type="number" min={1} max={365} value={horizon} onChange={e=>setHorizon(Number(e.target.value))}/></label></div><div className="form-row"><label>Fréquence<select value={frequency} onChange={e=>setFrequency(e.target.value)}><option value="auto">Auto</option><option value="daily">Quotidienne</option><option value="weekly">Hebdomadaire</option><option value="monthly">Mensuelle</option><option value="quarterly">Trimestrielle</option><option value="yearly">Annuelle</option></select></label><label>Méthode<select value={method} onChange={e=>setMethod(e.target.value)}><option value="auto">Comparer automatiquement</option><option value="naive">Naïve</option><option value="seasonal_naive">Naïve saisonnière</option><option value="linear_trend">Tendance linéaire</option><option value="exponential_smoothing">Lissage exponentiel</option></select></label><RunButton busy={busy} label="Prévoir" busyLabel="Calcul…" onClick={run}/></div></div></Panel>
    {out&&<><div className="metrics"><Stat label="Méthode retenue" value={out.method}/><Stat label="Fréquence" value={out.frequency}/><Stat label="Validation" value={`${out.validation_periods} périodes`}/><Stat label="Horizon" value={`${out.horizon} périodes`}/></div><Panel title="Historique & prévision"><ForecastChart history={out.history} forecast={out.forecast}/></Panel><Panel title="Benchmark des méthodes"><SimpleTable rows={out.benchmark.filter((x:AnyObj)=>x.status==='ok')} columns={[["method","Méthode"],["mae","MAE"],["rmse","RMSE"],["mape","MAPE %"]]}/></Panel><Panel title="Prévisions"><SimpleTable rows={out.forecast} columns={[["date","Date"],["prediction","Prévision"],["lower_95","Borne basse 95 %"],["upper_95","Borne haute 95 %"]]}/></Panel></>}
  </div>;
}

function ForecastChart({history,forecast}:{history:AnyObj[];forecast:AnyObj[]}) {
  const hist=history??[], fut=forecast??[]; const all=[...hist.map(x=>Number(x.value)),...fut.map(x=>Number(x.prediction)),...fut.map(x=>Number(x.lower_95)),...fut.map(x=>Number(x.upper_95))].filter(Number.isFinite); if(!all.length)return <div className="quiet-empty">Aucune donnée à tracer.</div>; const min=Math.min(...all),max=Math.max(...all),span=Math.max(1e-9,max-min); const total=Math.max(2,hist.length+fut.length); const x=(i:number)=>35+i/(total-1)*760; const y=(v:number)=>235-(v-min)/span*195; const hp=hist.map((r,i)=>`${x(i)},${y(Number(r.value))}`).join(' '); const fp=fut.map((r,i)=>`${x(hist.length+i)},${y(Number(r.prediction))}`).join(' '); const upper=fut.map((r,i)=>`${x(hist.length+i)},${y(Number(r.upper_95))}`).join(' '); const lower=[...fut].reverse().map((r,rev)=>`${x(hist.length+fut.length-1-rev)},${y(Number(r.lower_95))}`).join(' ');
  return <svg viewBox="0 0 830 260" className="forecast-chart"><line x1="35" y1="235" x2="800" y2="235" className="chart-axis"/><line x1="35" y1="40" x2="35" y2="235" className="chart-axis"/><polygon points={`${upper} ${lower}`} className="forecast-band"/>{hp&&<polyline points={hp} className="history-line" fill="none"/>}{fp&&<polyline points={fp} className="forecast-line" fill="none"/>}<text x="38" y="30" className="chart-label">{formatNumber(max)}</text><text x="38" y="252" className="chart-label">{formatNumber(min)}</text><text x="650" y="28" className="chart-label">Prévision + IC 95%</text></svg>;
}

function AnomalyView({ result, setError }: { result:AnyObj|null; setError:(s:string)=>void }) {
  const numeric=(result?.profile?.columns??[]).filter(isNumeric); const [selected,setSelected]=useState<string[]>([]); const [method,setMethod]=useState('auto'); const [contamination,setContamination]=useState(0.05); const [out,setOut]=useState<AnyObj|null>(null); const [busy,setBusy]=useState(false);
  useEffect(()=>{if(result){setSelected(numeric.slice(0,Math.min(3,numeric.length)).map((c:AnyObj)=>c.name));setOut(null);}},[result?.dataset?.id]);
  if(!result)return <EmptyState title="Détection d’anomalies" text="Chargez un dataset contenant des variables numériques."/>;
  async function run(){setBusy(true);setError('');try{setOut(await runAnomalyDetection(result!.dataset.id,{columns:selected,method,contamination,threshold:3.5}));}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <div className="page"><div className="page-title"><div><span className="eyebrow">ANOMALY DETECTION</span><h1>Anomalies</h1><p>IQR, z-score robuste ou Isolation Forest multivarié. Les observations originales ne sont jamais modifiées.</p></div><span className="module-state implemented">implémenté</span></div><div className="two-col"><Panel title="Variables"><div className="check-grid">{numeric.map((c:AnyObj)=><label key={c.name}><input type="checkbox" checked={selected.includes(c.name)} onChange={e=>setSelected(e.target.checked?[...selected,c.name]:selected.filter(x=>x!==c.name))}/>{c.name}</label>)}</div></Panel><Panel title="Méthode"><div className="stack-form"><label>Moteur<select value={method} onChange={e=>setMethod(e.target.value)}><option value="auto">Auto</option><option value="iqr">IQR</option><option value="robust_z">Z-score robuste</option><option value="isolation_forest">Isolation Forest</option></select></label><label>Contamination Isolation Forest<input type="number" min={0.001} max={0.4} step={0.01} value={contamination} onChange={e=>setContamination(Number(e.target.value))}/></label><RunButton busy={busy} label="Détecter" busyLabel="Analyse…" onClick={run}/></div></Panel></div>{out&&<><div className="metrics"><Stat label="Méthode" value={out.method}/><Stat label="Observations" value={out.rows}/><Stat label="Anomalies" value={out.anomalies_count}/><Stat label="Taux" value={`${formatNumber(out.anomaly_rate_pct)} %`}/></div><Panel title="Anomalies les plus importantes"><SimpleTable rows={out.anomalies.slice(0,100).map((a:AnyObj)=>({index:a.index,score:a.score,reasons:(a.reasons??[]).join('; '),values:JSON.stringify(a.values)}))} columns={[["index","Index"],["score","Score"],["reasons","Raison"],["values","Valeurs"]]}/></Panel></>}</div>;
}

function XaiView({ result, model, setError }: { result:AnyObj|null; model:AnyObj|null; setError:(s:string)=>void }) {
  const [diag,setDiag]=useState<AnyObj|null>(null); const [local,setLocal]=useState<AnyObj|null>(null); const [rowText,setRowText]=useState('{}'); const [busy,setBusy]=useState(false); const [explaining,setExplaining]=useState(false);
  useEffect(()=>{setDiag(null);setLocal(null);if(model&&result){const features=model.model_card?.features??model.model_card?.features??[];const source=result.preview?.rows?.[0]??{};const row:AnyObj={};for(const f of features){if(f in source)row[f]=source[f];}setRowText(JSON.stringify(row,null,2));}},[model?.model_id,result?.dataset?.id]);
  if(!model)return <EmptyState title="Explicabilité XAI" text="Entraînez d’abord un modèle v0.8+ dans l’onglet Modélisation."/>;
  async function load(){setBusy(true);setError('');try{setDiag(await getModelDiagnostics(model!.model_id));}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  async function explain(){setExplaining(true);setError('');try{setLocal(await explainModelPrediction(model!.model_id,JSON.parse(rowText)));}catch(e:unknown){setError(e instanceof Error?e.message:String(e));}finally{setExplaining(false);}}
  return <div className="page"><div className="page-title"><div><span className="eyebrow">EXPLAINABLE AI</span><h1>Explicabilité du modèle</h1><p>Diagnostics globaux, importance par permutation, calibration binaire et explication locale par perturbation contrôlée.</p></div><span className="module-state implemented">XAI core</span></div><Panel title="Diagnostics globaux" action={<code>{model.model_id.slice(0,8)}…</code>}><div className="button-row"><RunButton busy={busy} label="Calculer les diagnostics" busyLabel="Calcul…" onClick={load}/>{diag&&<small className="help-text">Évaluation : {diag.evaluation_source} · {diag.rows} lignes</small>}</div></Panel>{diag&&<><Panel title="Importance globale"><BarChart rows={(diag.permutation_importance??[]).slice(0,12).map((x:AnyObj)=>({...x,importance_abs:Math.abs(Number(x.importance)||0)}))} valueKey="importance_abs" labelKey="feature"/></Panel>{diag.task==='classification'&&<><div className="two-col"><Panel title="Matrice de confusion"><ConfusionMatrix matrix={diag.confusion_matrix} classes={diag.classes}/></Panel><Panel title="Courbe ROC"><div className="metrics mini"><Stat label="ROC-AUC" value={formatNumber(diag.roc_auc)}/><Stat label="Brier" value={formatNumber(diag.brier_score)}/></div>{diag.roc_curve&&<CurveChart rows={diag.roc_curve} xKey="fpr" yKey="tpr"/>}</Panel></div><div className="two-col"><Panel title="Precision / Recall">{diag.pr_curve&&<CurveChart rows={diag.pr_curve} xKey="recall" yKey="precision"/>}</Panel><Panel title="Calibration binaire">{diag.calibration&&<CurveChart rows={diag.calibration} xKey="mean_predicted" yKey="fraction_positive"/>}</Panel></div></>}{diag.task==='regression'&&<Panel title="Résidus"><div className="metrics"><Stat label="MAE" value={formatNumber(diag.metrics?.mae)}/><Stat label="RMSE" value={formatNumber(diag.metrics?.rmse)}/><Stat label="R²" value={formatNumber(diag.metrics?.r2)}/><Stat label="Écart-type résidus" value={formatNumber(diag.metrics?.residual_std)}/></div></Panel>}</>}<Panel title="Explication locale"><textarea className="json-editor compact-editor" value={rowText} onChange={e=>setRowText(e.target.value)} spellCheck={false}/><RunButton busy={explaining} label="Expliquer cette prédiction" busyLabel="Explication…" onClick={explain}/>{local&&<div className="local-xai"><div className="advisor-box"><span>PRÉDICTION</span><b>{formatNumber(local.prediction)}</b><p>Méthode : {local.method}</p></div><SimpleTable rows={local.contributions} columns={[["feature","Variable"],["value","Valeur"],["baseline","Baseline"],["effect","Effet local"]]}/><small className="help-text">{local.caveat}</small></div>}</Panel></div>;
}

function ConfusionMatrix({matrix,classes}:{matrix:number[][];classes:any[]}) { if(!matrix?.length)return <div className="quiet-empty">Indisponible</div>; return <div className="confusion-grid" style={{gridTemplateColumns:`80px repeat(${classes.length},minmax(60px,1fr))`}}><span></span>{classes.map(c=><b key={`h${c}`}>Prédit {String(c)}</b>)}{matrix.map((row,i)=><><b key={`r${i}`}>Réel {String(classes[i])}</b>{row.map((v,j)=><span key={`${i}-${j}`} className={i===j?'correct':''}>{v}</span>)}</>)}</div>; }
function CurveChart({rows,xKey,yKey}:{rows:AnyObj[];xKey:string;yKey:string}) { if(!rows?.length)return <div className="quiet-empty">Courbe indisponible</div>; const pts=rows.map(r=>`${30+(Number(r[xKey])||0)*250},${220-(Number(r[yKey])||0)*180}`).join(' '); return <svg viewBox="0 0 300 240" className="curve-chart"><line x1="30" y1="220" x2="280" y2="220" className="chart-axis"/><line x1="30" y1="40" x2="30" y2="220" className="chart-axis"/><line x1="30" y1="220" x2="280" y2="40" className="reference-line"/><polyline points={pts} className="roc-line" fill="none"/></svg>; }


function AIAnalystView({ result, setError }: { result: AnyObj|null; setError:(s:string)=>void }) {
  const [question,setQuestion]=useState('Analyse ce dataset et identifie les principaux problèmes, relations et anomalies.');
  const [mode,setMode]=useState<'auto'|'fast'|'deep'>('auto');
  const [target,setTarget]=useState('');
  const [dateColumn,setDateColumn]=useState('');
  const [horizon,setHorizon]=useState(12);
  const [busy,setBusy]=useState(false);
  const [out,setOut]=useState<AnyObj|null>(null);
  const [capabilities,setCapabilities]=useState<AnyObj|null>(null);
  useEffect(()=>{if(!result)return; getAIAnalystCapabilities(result.dataset.id).then(setCapabilities).catch(()=>{});},[result?.dataset?.id]);
  if(!result) return <EmptyState title="AI Analyst" text="Chargez un dataset pour lancer une analyse orchestrée en langage naturel."/>;
  const columns=result.profile.columns ?? [];
  async function run(){
    if(!question.trim()) return;
    setBusy(true); setError('');
    try{
      setOut(await runAIAnalysis(result!.dataset.id,{question:question.trim(),target:target||null,date_column:dateColumn||null,horizon,mode}));
    }catch(e:unknown){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }
  const examples=[
    'Analyse ce dataset et identifie les principaux problèmes, relations et anomalies.',
    'Quelles sont les corrélations les plus importantes ?',
    'Détecte les anomalies dans les variables numériques.',
    'Compare les groupes et indique s’il existe une différence significative.',
    'Construis un modèle prédictif pour la variable cible.',
    'Prévois la variable cible sur les 12 prochaines périodes.'
  ];
  return <div className="page ai-analyst-page">
    <div className="page-title"><div><span className="eyebrow">AI ANALYST · TOOL ORCHESTRATION</span><h1>AI Analyst</h1><p>Décrivez votre objectif en langage naturel. L’orchestrateur construit un plan, exécute les moteurs analytiques réels, contrôle les résultats et expose leur provenance.</p></div><span className="module-state implemented">implémenté v0.9</span></div>
    <div className="ai-layout">
      <section className="ai-console">
        <div className="ai-console-head"><div><b>Demande analytique</b><span>Les nombres proviennent des outils exécutables, jamais d’un LLM.</span></div><span className="ai-engine-chip">{capabilities?.engine ?? 'deterministic_orchestrator'}</span></div>
        <textarea className="ai-prompt" value={question} onChange={e=>setQuestion(e.target.value)} spellCheck={false}/>
        <div className="ai-options">
          <label>Mode<select value={mode} onChange={e=>setMode(e.target.value as any)}><option value="fast">Rapide</option><option value="auto">Auto</option><option value="deep">Approfondi</option></select></label>
          <label>Cible (optionnel)<select value={target} onChange={e=>setTarget(e.target.value)}><option value="">Détection automatique</option>{columns.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label>
          <label>Date (optionnel)<select value={dateColumn} onChange={e=>setDateColumn(e.target.value)}><option value="">Détection automatique</option>{columns.map((c:AnyObj)=><option key={c.name}>{c.name}</option>)}</select></label>
          <label>Horizon<input type="number" min={1} max={365} value={horizon} onChange={e=>setHorizon(Number(e.target.value))}/></label>
        </div>
        <div className="ai-run-row"><RunButton busy={busy} label="Exécuter l’analyse" busyLabel="Orchestration…" onClick={run}/><small>Dataset : {result.dataset.name} · version {result.dataset.version ?? 1}</small></div>
      </section>
      <aside className="ai-examples"><b>Exemples</b>{examples.map(x=><button key={x} onClick={()=>setQuestion(x)}>{x}</button>)}</aside>
    </div>
    {out&&<>
      <Panel title="Réponse synthétique" action={<span className="ai-intent">intention : {out.intent}</span>}><div className="ai-answer">{out.answer}</div></Panel>
      <div className="two-col">
        <Panel title="Plan exécuté"><div className="ai-plan">{out.plan.map((p:AnyObj,i:number)=>{const exec=out.executions.find((e:AnyObj)=>e.tool===p.tool);return <div key={`${p.tool}-${i}`}><span>{String(p.step).padStart(2,'0')}</span><div><b>{p.action}</b><small>{p.tool} · {exec?.status ?? 'planned'}{exec?.duration_ms!=null?` · ${exec.duration_ms} ms`:''}</small></div><i className={exec?.status==='ok'?'ok':'bad'}>{exec?.status==='ok'?'✓':'!'}</i></div>})}</div></Panel>
        <Panel title="Critic / Validation"><div className={`critic-status ${out.critic.status}`}>{out.critic.status==='passed'?'VALIDÉ':'À VÉRIFIER'}</div><div className="critic-checks">{out.critic.checks.map((c:AnyObj)=><div key={c.check}><b>{c.passed?'✓':'!'}</b><span>{c.detail}</span></div>)}</div></Panel>
      </div>
      <Panel title="Constats vérifiables"><div className="ai-findings">{out.findings.map((f:AnyObj,i:number)=><article key={i} className={`ai-finding ${f.level}`}><div><span>{f.level}</span><b>{f.title}</b></div><p>{f.statement}</p><code>{f.evidence?.tool}</code></article>)}</div></Panel>
      <Panel title="Provenance"><div className="provenance-grid"><div><span>Dataset</span><b>{out.provenance.dataset_name}</b></div><div><span>Version</span><b>{out.provenance.dataset_version}</b></div><div><span>Calcul</span><b>{out.provenance.calculation_policy}</b></div><div><span>Outils</span><b>{(out.provenance.tools_executed??[]).join(', ')}</b></div></div></Panel>
      <Panel title="Résultats techniques"><details><summary>Afficher les sorties des moteurs</summary><pre className="result-json ai-json">{JSON.stringify(out.artifacts,null,2)}</pre></details></Panel>
    </>}
  </div>;
}

function PlannedView({ view }: { view: View }) { const meta:Record<string,{title:string;desc:string;items:string[]}>= {report:{title:'Rapports',desc:'Génération reproductible de rapports à partir des résultats calculés et des visualisations.',items:['Blocs texte, tableaux et graphiques','Méthodologie et provenance','Export PDF / HTML / DOCX','Rejouer une analyse']}}; const m=meta[view]; if(!m) return null; return <div className="page"><div className="page-title"><div><span className="eyebrow">PLANIFIÉ</span><h1>{m.title}</h1><p>{m.desc}</p></div><span className="module-state planned">à implémenter</span></div><div className="planned-card"><div className="planned-grid">{m.items.map((x,i)=><div key={x}><span>{String(i+1).padStart(2,'0')}</span><b>{x}</b></div>)}</div><p>Aucune donnée fictive n’est affichée ici : ce module sera activé quand son moteur d’exécution réel sera disponible.</p></div></div>; }
