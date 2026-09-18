const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8005/api/v1';

function enterpriseContextHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers ?? {});
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('dv_enterprise_token') || '';
    const workspace = localStorage.getItem('dv_enterprise_workspace') || '';
    if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`);
    if (workspace && !headers.has('X-Workspace-ID')) headers.set('X-Workspace-ID', workspace);
  }
  return headers;
}

/** Every API call carries the active Enterprise context when one exists.
 * This prevents legacy analysis calls from accidentally bypassing v2.2 governance.
 */
async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  return fetch(input, { ...init, headers: enterpriseContextHeaders(init) });
}

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
  const headers: Record<string,string> = {};
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('dv_enterprise_token') || '';
    const workspace = localStorage.getItem('dv_enterprise_workspace') || '';
    if (token && workspace) {
      headers.Authorization = `Bearer ${token}`;
      headers['X-Workspace-ID'] = workspace;
    }
  }
  return parse<any>(await apiFetch(`${API}/datasets`, { method: 'POST', body, headers }), 'Upload impossible');
}

export async function getProfile(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/profile`), 'Profilage impossible');
}

export async function getDatasetAccessContext(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/access-context`), 'Contexte d’accès indisponible');
}

export async function getQuality(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/quality`), 'Qualité impossible');
}

export async function getDecision(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/decision-support`), 'Décision impossible');
}

export async function getPreview(id: string, limit = 25) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/preview?limit=${limit}`), 'Aperçu impossible');
}

export async function getColumnAnalysis(id: string, column: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/columns/${encodeURIComponent(column)}/analysis`), 'Analyse de variable impossible');
}

export async function trainModel(id: string, payload: { target: string; task: string; algorithm: string }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/models/train`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }), 'Entraînement impossible');
}

export async function predictModel(modelId: string, rows: Record<string, unknown>[]) {
  return parse<any>(await apiFetch(`${API}/datasets/models/${modelId}/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows }),
  }), 'Prédiction impossible');
}

export async function runRegression(id: string, payload: { dependent: string; independents: string[] }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/analysis/regression`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Régression impossible');
}

export async function runAnova(id: string, payload: { response: string; factor1: string; factor2?: string | null }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/analysis/anova`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'ANOVA impossible');
}

export async function runPca(id: string, payload: { columns: string[]; scale?: boolean }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/analysis/pca`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'ACP impossible');
}

export async function runClustering(id: string, payload: { columns: string[]; k: number }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/analysis/clustering`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Clustering impossible');
}

export async function getDataset(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}`), 'Métadonnées du dataset indisponibles');
}

export async function getVersions(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/versions`), 'Historique des versions indisponible');
}

export async function transformDataset(id: string, operation: Record<string, unknown>) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/transform`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ operation }),
  }), 'Transformation impossible');
}

export async function getDatasetCatalog() {
  return parse<any>(await apiFetch(`${API}/datasets/catalog/all`), 'Catalogue des datasets indisponible');
}

export async function combineDataset(id: string, otherDatasetId: string, operation: Record<string, unknown>) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/combine`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ other_dataset_id: otherDatasetId, operation }),
  }), 'Combinaison impossible');
}

export async function getPipelines(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/pipelines`), 'Pipelines indisponibles');
}

export async function savePipeline(id: string, name: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/pipelines`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
  }), 'Enregistrement du pipeline impossible');
}

export async function runPipeline(id: string, pipelineId: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/pipelines/${pipelineId}/run`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
  }), 'Exécution du pipeline impossible');
}

export async function runCorrelations(id: string, payload: { columns: string[]; method: 'pearson'|'spearman' }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/analysis/correlations`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Corrélations impossibles');
}

export async function runStatisticalTest(id: string, payload: Record<string, unknown>) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/analysis/statistical-test`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Test statistique impossible');
}

export async function getTestAdvice(id: string, payload: Record<string, unknown>) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/analysis/test-advisor`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Conseil statistique indisponible');
}

export async function getEngineInfo(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/workspace/engine`), 'Informations moteur indisponibles');
}

export async function runSql(id: string, sql: string, limit = 500) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/workspace/sql`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sql, limit }),
  }), 'Exécution SQL impossible');
}

export async function recommendVisualizations(id: string, columns: string[]) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/visualizations/recommend`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ columns }),
  }), 'Recommandations de visualisation indisponibles');
}

export async function buildVisualization(id: string, payload: Record<string, unknown>) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/visualizations/build`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Visualisation impossible');
}

export async function runAutoML(id: string, payload: { target: string; task?: string; primary_metric?: string; cv_folds?: number; tune?: boolean; max_candidates?: number }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/models/automl`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'AutoML impossible');
}

export async function getModelCard(modelId: string) {
  return parse<any>(await apiFetch(`${API}/datasets/models/${modelId}/card`), 'Model Card indisponible');
}

export async function getModels(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/models`), 'Registre des modèles indisponible');
}

export async function runForecast(id: string, payload: { date_column: string; target: string; horizon?: number; frequency?: string; method?: string }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/analysis/forecast`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Forecasting impossible');
}

export async function runAnomalyDetection(id: string, payload: { columns: string[]; method?: string; contamination?: number; threshold?: number }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/analysis/anomalies`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Détection d’anomalies impossible');
}

export async function getModelDiagnostics(modelId: string) {
  return parse<any>(await apiFetch(`${API}/datasets/models/${modelId}/diagnostics`), 'Diagnostics XAI indisponibles');
}

export async function explainModelPrediction(modelId: string, row: Record<string, unknown>) {
  return parse<any>(await apiFetch(`${API}/datasets/models/${modelId}/explain`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ row }),
  }), 'Explication locale impossible');
}


export async function getAIAnalystCapabilities(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/ai/capabilities`), 'Capacités AI Analyst indisponibles');
}

export async function runAIAnalysis(id: string, payload: { question: string; target?: string | null; date_column?: string | null; variables?: string[]; group?: string | null; horizon?: number; mode?: 'auto'|'fast'|'deep' }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/ai/analyze`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Analyse AI impossible');
}

export async function runNaturalLanguageQuery(id: string, question: string, limit = 200) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/workspace/nlq`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, limit }),
  }), 'Question en langage naturel impossible');
}

export async function getAIHistory(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/ai/history`), 'Historique AI Analyst indisponible');
}

export async function getAIHistoryItem(id: string, sessionId: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/ai/history/${sessionId}`), 'Analyse AI introuvable');
}

export async function getReports(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/reports`), 'Rapports indisponibles');
}

export async function createReport(id: string, payload: { title: string; subtitle?: string | null; author?: string | null; organization?: string | null; template?: 'executive'|'analytical'|'technical'; sections: string[]; analysis_session_id?: string | null; visualization_ids?: string[]; auto_story?: boolean; auto_visualizations?: boolean; max_visualizations?: number }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/reports`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Création du rapport impossible');
}

export async function downloadReport(id: string, reportId: string, format: 'pdf'|'docx'|'html'|'md') {
  const res = await apiFetch(`${API}/datasets/${id}/reports/${reportId}/export/${format}`);
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
  return parse<any>(await apiFetch(`${API}/datasets/${id}/dashboard`), 'Dashboard analytique indisponible');
}

export async function getSavedVisualizations(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/visualizations/saved`), 'Visualisations enregistrées indisponibles');
}

export async function saveVisualization(id: string, title: string, visualization: Record<string, unknown>) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/visualizations/saved`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, visualization }),
  }), 'Enregistrement de la visualisation impossible');
}

export async function getDashboards(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/dashboards`), 'Dashboards indisponibles');
}

export async function getDashboardDefinition(id: string, dashboardId: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/dashboards/${dashboardId}`), 'Dashboard introuvable');
}

export async function saveDashboardDefinition(id: string, payload: { dashboard_id?: string | null; name: string; description?: string; filters: Record<string, unknown>[]; widgets: Record<string, unknown>[] }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/dashboards`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Enregistrement du dashboard impossible');
}

export async function deleteDashboardDefinition(id: string, dashboardId: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/dashboards/${dashboardId}`, { method: 'DELETE' }), 'Suppression du dashboard impossible');
}

export async function previewDashboard(id: string, payload: { filters: Record<string, unknown>[]; widgets: Record<string, unknown>[] }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/dashboards/preview`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Aperçu du dashboard impossible');
}

export async function getSemanticModel(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/semantic`), 'Couche sémantique indisponible');
}

export async function saveSemanticModel(id: string, payload: { tables?: any[]; relationships?: any[]; metrics: any[]; dimensions: any[]; hierarchies?: any[]; business_glossary?: any[] }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/semantic`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Enregistrement de la couche sémantique impossible');
}

export async function getSemanticTableCatalog(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/semantic/tables`), 'Catalogue sémantique indisponible');
}

export async function validateSemanticModel(id: string, payload: { tables?: any[]; relationships?: any[]; metrics: any[]; dimensions: any[]; hierarchies?: any[]; business_glossary?: any[] }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/semantic/validate`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Validation du modèle sémantique impossible');
}

export async function querySemanticMetric(id: string, payload: { metric_id: string; dimensions?: string[]; filters?: any[]; limit?: number; date_dimension?: string | null; time_grain?: string | null; comparison?: string; time_calculation?: string; rolling_window?: number }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/semantic/query`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Requête sémantique impossible');
}

export async function evaluateSemanticMetric(id: string, payload: { metric_id: string; dimensions?: string[]; filters?: any[]; limit?: number }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/semantic/evaluate`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Calcul de métrique impossible');
}

export async function getMetricPulse(id: string, payload: { metric_id: string; date_column?: string | null; periods?: number }) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/semantic/pulse`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Pulse métrique indisponible');
}

export async function getTrustCenter(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/trust`), 'Trust Center indisponible');
}

export async function runModelWhatIf(modelId: string, payload: { base_row: Record<string, unknown>; scenarios: any[] }) {
  return parse<any>(await apiFetch(`${API}/datasets/models/${modelId}/what-if`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Simulation what-if impossible');
}

export async function runModelSensitivity(modelId: string, payload: { base_row: Record<string, unknown>; feature: string; values: any[] }) {
  return parse<any>(await apiFetch(`${API}/datasets/models/${modelId}/sensitivity`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }), 'Analyse de sensibilité impossible');
}


export async function getProactiveSummary(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/proactive/summary`), 'Synthèse proactive indisponible');
}

export async function getProactiveWatches(id: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/proactive/watches`), 'Surveillances indisponibles');
}

export async function autoConfigureProactiveWatches(id: string, payload: { threshold_pct?: number; time_grain?: string } = {}) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/proactive/watches/auto`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload),
  }), 'Configuration automatique des surveillances impossible');
}

export async function saveProactiveWatch(id: string, payload: Record<string, unknown>) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/proactive/watches`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload),
  }), 'Enregistrement de la surveillance impossible');
}

export async function deleteProactiveWatch(id: string, watchId: string) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/proactive/watches/${watchId}`, { method:'DELETE' }), 'Suppression de la surveillance impossible');
}

export async function scanProactiveSignals(id: string, payload: { watch_ids?: string[]; auto_configure?: boolean } = {}) {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/proactive/scan`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload),
  }), 'Scan proactif impossible');
}

export async function getProactiveInbox(id: string, status='all', limit=100) {
  const params=new URLSearchParams({status,limit:String(limit)});
  return parse<any>(await apiFetch(`${API}/datasets/${id}/proactive/inbox?${params.toString()}`), 'Inbox analytique indisponible');
}

export async function updateProactiveAlertStatus(id: string, alertId: string, status: 'open'|'acknowledged'|'dismissed'|'resolved') {
  return parse<any>(await apiFetch(`${API}/datasets/${id}/proactive/inbox/${alertId}/status`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({status}),
  }), 'Mise à jour de l’alerte impossible');
}

function enterpriseHeaders(token?: string): Record<string,string> {
  const headers: Record<string,string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export async function bootstrapEnterprise(payload: { email:string; password:string; display_name:string; organization_name:string }) {
  return parse<any>(await apiFetch(`${API}/auth/bootstrap`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) }), 'Initialisation Enterprise impossible');
}

export async function loginEnterprise(payload: { email:string; password:string }) {
  return parse<any>(await apiFetch(`${API}/auth/login`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) }), 'Connexion impossible');
}

export async function getEnterpriseSession(token:string) {
  return parse<any>(await apiFetch(`${API}/auth/me`, { headers: enterpriseHeaders(token) }), 'Session Enterprise indisponible');
}

export async function getEnterpriseStatus() {
  return parse<any>(await apiFetch(`${API}/enterprise/status`), 'Statut Enterprise indisponible');
}

export async function createEnterpriseWorkspace(token:string, organization_id:string, name:string) {
  return parse<any>(await apiFetch(`${API}/workspaces`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({organization_id,name}) }), 'Création du workspace impossible');
}

export async function getEnterpriseWorkspace(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}`, { headers:enterpriseHeaders(token) }), 'Workspace indisponible');
}

export async function addWorkspaceMember(token:string, workspace_id:string, email:string, role:string, display_name?:string, password?:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/members`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({email,role,display_name:display_name||null,password:password||null}) }), 'Ajout du membre impossible');
}

export async function bindWorkspaceDataset(token:string, workspace_id:string, dataset_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/datasets`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({dataset_id}) }), 'Liaison du dataset impossible');
}

export async function saveWorkspacePolicy(token:string, workspace_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/policies`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Enregistrement de la politique impossible');
}

export async function getAuditEvents(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/audit?workspace_id=${encodeURIComponent(workspace_id)}&limit=200`, { headers:enterpriseHeaders(token) }), 'Journal d’audit indisponible');
}

export async function getEnterpriseJobs(token:string, workspace_id?:string) {
  const suffix=workspace_id?`?workspace_id=${encodeURIComponent(workspace_id)}`:'';
  return parse<any>(await apiFetch(`${API}/jobs${suffix}`, { headers:enterpriseHeaders(token) }), 'Jobs indisponibles');
}

export async function submitEnterpriseJob(token:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/jobs`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Soumission du job impossible');
}

export async function cancelEnterpriseJob(token:string, job_id:string) {
  return parse<any>(await apiFetch(`${API}/jobs/${job_id}/cancel`, { method:'POST', headers:enterpriseHeaders(token) }), 'Annulation du job impossible');
}

export async function getGovernedPreview(token:string, workspace_id:string, dataset_id:string, limit=50, simulate_role?:string) {
  const params=new URLSearchParams({limit:String(limit)}); if(simulate_role)params.set('simulate_role',simulate_role);
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/datasets/${dataset_id}/governed-preview?${params.toString()}`, { headers:enterpriseHeaders(token) }), 'Aperçu gouverné indisponible');
}

export async function getReviewSummary(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/reviews/summary`, { headers:enterpriseHeaders(token) }), 'Synthèse des revues indisponible');
}

export async function getReviews(token:string, workspace_id:string, status='all', scope='all') {
  const params=new URLSearchParams({status,scope});
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/reviews?${params.toString()}`, { headers:enterpriseHeaders(token) }), 'Revues indisponibles');
}

export async function getReviewDetail(token:string, workspace_id:string, review_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/reviews/${review_id}`, { headers:enterpriseHeaders(token) }), 'Détail de la revue indisponible');
}

export async function createReview(token:string, workspace_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/reviews`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Création de la revue impossible');
}

export async function assignReview(token:string, workspace_id:string, review_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/reviews/${review_id}/assign`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Affectation de la revue impossible');
}

export async function transitionReview(token:string, workspace_id:string, review_id:string, action:string, note='') {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/reviews/${review_id}/transition`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({action,note}) }), 'Transition de revue impossible');
}

export async function addReviewComment(token:string, workspace_id:string, review_id:string, body:string, mention_user_ids:string[] = []) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/reviews/${review_id}/comments`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({body,mention_user_ids}) }), 'Commentaire impossible');
}

export async function resolveReviewComment(token:string, workspace_id:string, review_id:string, comment_id:string, resolved=true) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/reviews/${review_id}/comments/${comment_id}/resolve`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({resolved}) }), 'Mise à jour du commentaire impossible');
}

export async function getCollaborationNotifications(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/collaboration/notifications`, { headers:enterpriseHeaders(token) }), 'Notifications de collaboration indisponibles');
}

export async function markCollaborationNotificationRead(token:string, workspace_id:string, notification_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/collaboration/notifications/${notification_id}/read`, { method:'POST', headers:enterpriseHeaders(token) }), 'Lecture de la notification impossible');
}

export async function getCertifications(token:string, workspace_id:string, status='active') {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/certifications?status=${encodeURIComponent(status)}`, { headers:enterpriseHeaders(token) }), 'Certifications indisponibles');
}

export async function certifyReview(token:string, workspace_id:string, review_id:string, payload:{valid_until?:string|null;notes?:string}) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/reviews/${review_id}/certify`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Certification impossible');
}

export async function revokeCertification(token:string, workspace_id:string, certification_id:string, note='') {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/certifications/${certification_id}/revoke`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({note}) }), 'Révocation impossible');
}

// ---------------------------- Data connectors & refresh v2.7 ----------------------------
export async function getConnectorOverview(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/connectors`, { headers:enterpriseHeaders(token) }), 'Connecteurs indisponibles');
}

export async function getConnectorHealth(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/connectors/health`, { headers:enterpriseHeaders(token) }), 'Santé des connecteurs indisponible');
}

export async function createDataConnector(token:string, workspace_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/connectors`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Création du connecteur impossible');
}

export async function updateDataConnector(token:string, workspace_id:string, connector_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/connectors/${connector_id}`, { method:'PATCH', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Mise à jour du connecteur impossible');
}

export async function deleteDataConnector(token:string, workspace_id:string, connector_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/connectors/${connector_id}`, { method:'DELETE', headers:enterpriseHeaders(token) }), 'Suppression du connecteur impossible');
}

export async function testDataConnector(token:string, workspace_id:string, connector_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/connectors/${connector_id}/test`, { method:'POST', headers:enterpriseHeaders(token) }), 'Test du connecteur impossible');
}

export async function discoverDataConnector(token:string, workspace_id:string, connector_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/connectors/${connector_id}/discover`, { headers:enterpriseHeaders(token) }), 'Découverte des tables impossible');
}

export async function createConnectorSource(token:string, workspace_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/sources`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Création de la source impossible');
}

export async function deleteConnectorSource(token:string, workspace_id:string, source_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/sources/${source_id}`, { method:'DELETE', headers:enterpriseHeaders(token) }), 'Suppression de la source impossible');
}

export async function previewConnectorSource(token:string, workspace_id:string, source_id:string, limit=25) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/sources/${source_id}/preview?limit=${limit}`, { headers:enterpriseHeaders(token) }), 'Aperçu de la source impossible');
}

export async function refreshConnectorSource(token:string, workspace_id:string, source_id:string, background=true) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/sources/${source_id}/refresh`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({background}) }), 'Refresh impossible');
}

export async function saveConnectorSchedule(token:string, workspace_id:string, source_id:string, enabled:boolean, interval_minutes:number) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/sources/${source_id}/schedule`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({enabled,interval_minutes}) }), 'Planification du refresh impossible');
}

export async function getRefreshRuns(token:string, workspace_id:string, source_id?:string) {
  const params=new URLSearchParams(); if(source_id)params.set('source_id',source_id); params.set('limit','100');
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/refresh-runs?${params.toString()}`, { headers:enterpriseHeaders(token) }), 'Historique des refresh indisponible');
}
