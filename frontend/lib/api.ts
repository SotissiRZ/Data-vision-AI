const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8005/api/v1';

async function parse<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    let detail = fallback;
    try {
      const body = await res.json();
      detail = body.detail ?? fallback;
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function uploadDataset(file: File) {
  const body = new FormData();
  body.append('file', file);
  return parse<any>(await fetch(`${API}/datasets`, { method: 'POST', body }), 'Upload impossible');
}

export async function getProfile(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/profile`), 'Profilage impossible');
}

export async function getQuality(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/quality`), 'Qualité impossible');
}

export async function getDecision(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/decision-support`), 'Décision impossible');
}

export async function getPreview(id: string, limit = 25) {
  return parse<any>(await fetch(`${API}/datasets/${id}/preview?limit=${limit}`), 'Aperçu impossible');
}

export async function getColumnAnalysis(id: string, column: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/columns/${encodeURIComponent(column)}/analysis`), 'Analyse de variable impossible');
}

export async function trainModel(id: string, payload: { target: string; task: string; algorithm: string }) {
  return parse<any>(await fetch(`${API}/datasets/${id}/models/train`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }), 'Entraînement impossible');
}

export async function predictModel(modelId: string, rows: Record<string, unknown>[]) {
  return parse<any>(await fetch(`${API}/datasets/models/${modelId}/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows }),
  }), 'Prédiction impossible');
}

export async function runRegression(id: string, payload: { dependent: string; independents: string[] }) {
  return parse<any>(await fetch(`${API}/datasets/${id}/analysis/regression`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Régression impossible');
}

export async function runAnova(id: string, payload: { response: string; factor1: string; factor2?: string | null }) {
  return parse<any>(await fetch(`${API}/datasets/${id}/analysis/anova`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'ANOVA impossible');
}

export async function runPca(id: string, payload: { columns: string[]; scale?: boolean }) {
  return parse<any>(await fetch(`${API}/datasets/${id}/analysis/pca`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'ACP impossible');
}

export async function runClustering(id: string, payload: { columns: string[]; k: number }) {
  return parse<any>(await fetch(`${API}/datasets/${id}/analysis/clustering`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Clustering impossible');
}

export async function getDataset(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}`), 'Métadonnées du dataset indisponibles');
}

export async function getVersions(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/versions`), 'Historique des versions indisponible');
}

export async function transformDataset(id: string, operation: Record<string, unknown>) {
  return parse<any>(await fetch(`${API}/datasets/${id}/transform`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ operation }),
  }), 'Transformation impossible');
}

export async function getDatasetCatalog() {
  return parse<any>(await fetch(`${API}/datasets/catalog/all`), 'Catalogue des datasets indisponible');
}

export async function combineDataset(id: string, otherDatasetId: string, operation: Record<string, unknown>) {
  return parse<any>(await fetch(`${API}/datasets/${id}/combine`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ other_dataset_id: otherDatasetId, operation }),
  }), 'Combinaison impossible');
}

export async function getPipelines(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/pipelines`), 'Pipelines indisponibles');
}

export async function savePipeline(id: string, name: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/pipelines`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
  }), 'Enregistrement du pipeline impossible');
}

export async function runPipeline(id: string, pipelineId: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/pipelines/${pipelineId}/run`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
  }), 'Exécution du pipeline impossible');
}

export async function runCorrelations(id: string, payload: { columns: string[]; method: 'pearson'|'spearman' }) {
  return parse<any>(await fetch(`${API}/datasets/${id}/analysis/correlations`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Corrélations impossibles');
}

export async function runStatisticalTest(id: string, payload: Record<string, unknown>) {
  return parse<any>(await fetch(`${API}/datasets/${id}/analysis/statistical-test`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Test statistique impossible');
}

export async function getTestAdvice(id: string, payload: Record<string, unknown>) {
  return parse<any>(await fetch(`${API}/datasets/${id}/analysis/test-advisor`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Conseil statistique indisponible');
}

export async function getEngineInfo(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/workspace/engine`), 'Informations moteur indisponibles');
}

export async function runSql(id: string, sql: string, limit = 500) {
  return parse<any>(await fetch(`${API}/datasets/${id}/workspace/sql`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sql, limit }),
  }), 'Exécution SQL impossible');
}

export async function recommendVisualizations(id: string, columns: string[]) {
  return parse<any>(await fetch(`${API}/datasets/${id}/visualizations/recommend`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ columns }),
  }), 'Recommandations de visualisation indisponibles');
}

export async function buildVisualization(id: string, payload: Record<string, unknown>) {
  return parse<any>(await fetch(`${API}/datasets/${id}/visualizations/build`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Visualisation impossible');
}

export async function runAutoML(id: string, payload: { target: string; task?: string; primary_metric?: string; cv_folds?: number; tune?: boolean; max_candidates?: number }) {
  return parse<any>(await fetch(`${API}/datasets/${id}/models/automl`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'AutoML impossible');
}

export async function getModelCard(modelId: string) {
  return parse<any>(await fetch(`${API}/datasets/models/${modelId}/card`), 'Model Card indisponible');
}

export async function getModels(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/models`), 'Registre des modèles indisponible');
}

export async function runForecast(id: string, payload: { date_column: string; target: string; horizon?: number; frequency?: string; method?: string }) {
  return parse<any>(await fetch(`${API}/datasets/${id}/analysis/forecast`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Forecasting impossible');
}

export async function runAnomalyDetection(id: string, payload: { columns: string[]; method?: string; contamination?: number; threshold?: number }) {
  return parse<any>(await fetch(`${API}/datasets/${id}/analysis/anomalies`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Détection d’anomalies impossible');
}

export async function getModelDiagnostics(modelId: string) {
  return parse<any>(await fetch(`${API}/datasets/models/${modelId}/diagnostics`), 'Diagnostics XAI indisponibles');
}

export async function explainModelPrediction(modelId: string, row: Record<string, unknown>) {
  return parse<any>(await fetch(`${API}/datasets/models/${modelId}/explain`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ row }),
  }), 'Explication locale impossible');
}


export async function getAIAnalystCapabilities(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/ai/capabilities`), 'Capacités AI Analyst indisponibles');
}

export async function runAIAnalysis(id: string, payload: { question: string; target?: string | null; date_column?: string | null; variables?: string[]; group?: string | null; horizon?: number; mode?: 'auto'|'fast'|'deep' }) {
  return parse<any>(await fetch(`${API}/datasets/${id}/ai/analyze`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Analyse AI impossible');
}

export async function runNaturalLanguageQuery(id: string, question: string, limit = 200) {
  return parse<any>(await fetch(`${API}/datasets/${id}/workspace/nlq`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, limit }),
  }), 'Question en langage naturel impossible');
}

export async function getAIHistory(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/ai/history`), 'Historique AI Analyst indisponible');
}

export async function getAIHistoryItem(id: string, sessionId: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/ai/history/${sessionId}`), 'Analyse AI introuvable');
}

export async function getReports(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/reports`), 'Rapports indisponibles');
}

export async function createReport(id: string, payload: { title: string; subtitle?: string | null; author?: string | null; organization?: string | null; template?: 'executive'|'analytical'|'technical'; sections: string[]; analysis_session_id?: string | null; visualization_ids?: string[]; auto_story?: boolean; auto_visualizations?: boolean; max_visualizations?: number }) {
  return parse<any>(await fetch(`${API}/datasets/${id}/reports`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Création du rapport impossible');
}

export async function downloadReport(id: string, reportId: string, format: 'pdf'|'docx'|'html'|'md') {
  const res = await fetch(`${API}/datasets/${id}/reports/${reportId}/export/${format}`);
  if (!res.ok) {
    let detail = 'Export du rapport impossible';
    try { const body = await res.json(); detail = body.detail ?? detail; } catch {}
    throw new Error(detail);
  }
  const blob = await res.blob();
  const disposition = res.headers.get('content-disposition') ?? '';
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] ?? `datavision-report.${format}`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

export async function getDashboard(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/dashboard`), 'Dashboard analytique indisponible');
}

export async function getSavedVisualizations(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/visualizations/saved`), 'Visualisations enregistrées indisponibles');
}

export async function saveVisualization(id: string, title: string, visualization: Record<string, unknown>) {
  return parse<any>(await fetch(`${API}/datasets/${id}/visualizations/saved`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, visualization }),
  }), 'Enregistrement de la visualisation impossible');
}

export async function getDashboards(id: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/dashboards`), 'Dashboards indisponibles');
}

export async function getDashboardDefinition(id: string, dashboardId: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/dashboards/${dashboardId}`), 'Dashboard introuvable');
}

export async function saveDashboardDefinition(id: string, payload: { dashboard_id?: string | null; name: string; description?: string; filters: Record<string, unknown>[]; widgets: Record<string, unknown>[] }) {
  return parse<any>(await fetch(`${API}/datasets/${id}/dashboards`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Enregistrement du dashboard impossible');
}

export async function deleteDashboardDefinition(id: string, dashboardId: string) {
  return parse<any>(await fetch(`${API}/datasets/${id}/dashboards/${dashboardId}`, { method: 'DELETE' }), 'Suppression du dashboard impossible');
}

export async function previewDashboard(id: string, payload: { filters: Record<string, unknown>[]; widgets: Record<string, unknown>[] }) {
  return parse<any>(await fetch(`${API}/datasets/${id}/dashboards/preview`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Aperçu du dashboard impossible');
}
