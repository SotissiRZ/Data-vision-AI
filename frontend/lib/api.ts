const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8005/api/v1';

function enterpriseContextHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers ?? {});
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('dv_enterprise_token') || '';
    const workspace = localStorage.getItem('dv_enterprise_workspace') || '';
    if (token) headers.set('Authorization', `Bearer ${token}`);
    if (workspace && !headers.has('X-Workspace-ID')) headers.set('X-Workspace-ID', workspace);
  }
  return headers;
}

/** Every API call carries the active Enterprise context when one exists.
 * This prevents legacy analysis calls from accidentally bypassing v2.2 governance.
 */
let enterpriseRefreshPromise: Promise<any> | null = null;

async function refreshEnterpriseTokens() {
  if (typeof window === 'undefined') return null;
  const refresh = localStorage.getItem('dv_enterprise_refresh') || '';
  if (!refresh) return null;
  if (!enterpriseRefreshPromise) {
    enterpriseRefreshPromise = fetch(`${API}/auth/refresh`, {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({refresh_token: refresh}),
    }).then(async res => {
      if (!res.ok) throw new Error('Session expirée');
      const body = await res.json();
      localStorage.setItem('dv_enterprise_token', body.access_token);
      localStorage.setItem('dv_enterprise_refresh', body.refresh_token);
      return body;
    }).finally(() => { enterpriseRefreshPromise = null; });
  }
  return enterpriseRefreshPromise;
}

async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  let res = await fetch(input, { ...init, headers: enterpriseContextHeaders(init) });
  const target = String(input);
  if (res.status === 401 && typeof window !== 'undefined' && !target.includes('/auth/refresh') && !target.includes('/auth/login') && !target.includes('/auth/bootstrap')) {
    try {
      const refreshed = await refreshEnterpriseTokens();
      if (refreshed) { const headers=enterpriseContextHeaders(init); headers.set('Authorization',`Bearer ${refreshed.access_token}`); res = await fetch(input, { ...init, headers }); }
    } catch {
      localStorage.removeItem('dv_enterprise_token');
      localStorage.removeItem('dv_enterprise_refresh');
      window.dispatchEvent(new Event('datavision-enterprise-session'));
    }
  }
  return res;
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



export async function getEnterpriseMFAStatus(token:string) {
  return parse<any>(await apiFetch(`${API}/auth/mfa/status`, { headers:enterpriseHeaders(token) }), 'Statut MFA indisponible');
}
export async function beginEnterpriseWebAuthnRegistration(token:string) {
  return parse<any>(await apiFetch(`${API}/auth/mfa/webauthn/register/options`, { method:'POST', headers:enterpriseHeaders(token) }), 'Initialisation WebAuthn impossible');
}
export async function verifyEnterpriseWebAuthnRegistration(token:string, payload:{challenge_id:string;credential:Record<string,unknown>;label?:string}) {
  return parse<any>(await apiFetch(`${API}/auth/mfa/webauthn/register/verify`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Enregistrement WebAuthn impossible');
}
export async function disableEnterpriseWebAuthnCredential(token:string, credential_id:string) {
  return parse<any>(await apiFetch(`${API}/auth/mfa/webauthn/${credential_id}`, { method:'DELETE', headers:enterpriseHeaders(token) }), 'Désactivation WebAuthn impossible');
}
export async function verifyEnterpriseWebAuthnLogin(payload:{challenge_id:string;credential:Record<string,unknown>}) {
  return parse<any>(await apiFetch(`${API}/auth/mfa/webauthn/login/verify`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) }), 'Validation MFA impossible');
}
export async function getEnterpriseSession(token:string) {
  return parse<any>(await apiFetch(`${API}/auth/me`, { headers: enterpriseHeaders(token) }), 'Session Enterprise indisponible');
}

export async function getEnterprisePreferences(token:string) {
  return parse<any>(await apiFetch(`${API}/auth/preferences`, { headers: enterpriseHeaders(token) }), 'Préférences utilisateur indisponibles');
}

export async function saveEnterprisePreferences(token:string, payload:{accessibility_mode?:'normal'|'comfortable'|'large';ui_zoom?:number;compact_navigation?:boolean}) {
  return parse<any>(await apiFetch(`${API}/auth/preferences`, { method:'PUT', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Enregistrement des préférences impossible');
}

export async function getEnterpriseStatus() {
  return parse<any>(await apiFetch(`${API}/enterprise/status`), 'Statut Enterprise indisponible');
}

export async function refreshEnterpriseSession(refresh_token:string) {
  return parse<any>(await fetch(`${API}/auth/refresh`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({refresh_token}) }), 'Rafraîchissement de session impossible');
}
export async function getEnterpriseAuthSessions(token:string) {
  return parse<any>(await apiFetch(`${API}/auth/sessions`, { headers:enterpriseHeaders(token) }), 'Sessions indisponibles');
}
export async function revokeEnterpriseAuthSession(token:string, session_id:string) {
  return parse<any>(await apiFetch(`${API}/auth/sessions/${session_id}/revoke`, { method:'POST', headers:enterpriseHeaders(token) }), 'Révocation de session impossible');
}
export async function logoutAllEnterpriseSessions(token:string) {
  return parse<any>(await apiFetch(`${API}/auth/logout-all`, { method:'POST', headers:enterpriseHeaders(token) }), 'Révocation globale impossible');
}
export async function getPublicOIDCProviders() {
  return parse<any>(await apiFetch(`${API}/auth/oidc/providers`), 'Fournisseurs SSO indisponibles');
}
export async function startEnterpriseOIDC(provider_id:string, redirect_uri:string) {
  return parse<any>(await apiFetch(`${API}/auth/oidc/${provider_id}/start`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({redirect_uri}) }), 'Démarrage SSO impossible');
}
export async function exchangeEnterpriseOIDC(payload:{provider_id:string;code:string;state:string;redirect_uri:string}) {
  return parse<any>(await apiFetch(`${API}/auth/oidc/exchange`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) }), 'Connexion SSO impossible');
}
export async function getWorkspaceOIDCProviders(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/identity/oidc`, { headers:enterpriseHeaders(token) }), 'Fournisseurs OIDC indisponibles');
}
export async function createWorkspaceOIDCProvider(token:string, workspace_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/identity/oidc`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Création OIDC impossible');
}
export async function disableWorkspaceOIDCProvider(token:string, workspace_id:string, provider_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/identity/oidc/${provider_id}`, { method:'DELETE', headers:enterpriseHeaders(token) }), 'Désactivation OIDC impossible');
}
export async function getWorkspaceSecrets(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/secrets`, { headers:enterpriseHeaders(token) }), 'Secrets indisponibles');
}
export async function createWorkspaceSecret(token:string, workspace_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/secrets`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Création du secret impossible');
}
export async function rotateWorkspaceSecret(token:string, workspace_id:string, secret_id:string, value:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/secrets/${secret_id}/rotate`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({value}) }), 'Rotation du secret impossible');
}
export async function testWorkspaceSecret(token:string, workspace_id:string, secret_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/secrets/${secret_id}/test`, { method:'POST', headers:enterpriseHeaders(token) }), 'Test du secret impossible');
}


export async function getWorkspacePlugins(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/plugins`, { headers:enterpriseHeaders(token) }), 'Plugins indisponibles');
}
export async function installWorkspacePlugin(token:string, workspace_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/plugins`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Installation du plugin impossible');
}
export async function updateWorkspacePlugin(token:string, workspace_id:string, plugin_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/plugins/${plugin_id}`, { method:'PATCH', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Mise à jour du plugin impossible');
}
export async function deleteWorkspacePlugin(token:string, workspace_id:string, plugin_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/plugins/${plugin_id}`, { method:'DELETE', headers:enterpriseHeaders(token) }), 'Suppression du plugin impossible');
}
export async function testWorkspacePlugin(token:string, workspace_id:string, plugin_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/plugins/${plugin_id}/test`, { method:'POST', headers:enterpriseHeaders(token) }), 'Test du plugin impossible');
}
export async function syncWorkspacePlugin(token:string, workspace_id:string, plugin_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/plugins/${plugin_id}/sync`, { method:'POST', headers:enterpriseHeaders(token) }), 'Synchronisation du plugin impossible');
}
export async function getWorkspacePluginDetail(token:string, workspace_id:string, plugin_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/plugins/${plugin_id}`, { headers:enterpriseHeaders(token) }), 'Détail du plugin indisponible');
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
export async function getConnectorCatalog(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/connectors/catalog`, { headers:enterpriseHeaders(token) }), 'Catalogue des connecteurs indisponible');
}

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

// ---------------------------- Data Reliability & Lineage v2.8 ----------------------------
export async function getReliabilitySummary(token:string, workspace_id:string, dataset_id?:string) {
  const params=new URLSearchParams(); if(dataset_id)params.set('dataset_id',dataset_id);
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/reliability/summary?${params.toString()}`, { headers:enterpriseHeaders(token) }), 'Synthèse de fiabilité indisponible');
}
export async function getDataContracts(token:string, workspace_id:string, dataset_id?:string) {
  const params=new URLSearchParams(); if(dataset_id)params.set('dataset_id',dataset_id);
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/contracts?${params.toString()}`, { headers:enterpriseHeaders(token) }), 'Data contracts indisponibles');
}
export async function saveDataContract(token:string, workspace_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/contracts`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Enregistrement du data contract impossible');
}
export async function deleteDataContract(token:string, workspace_id:string, contract_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/contracts/${contract_id}`, { method:'DELETE', headers:enterpriseHeaders(token) }), 'Suppression du data contract impossible');
}
export async function runDataContract(token:string, workspace_id:string, contract_id:string, dataset_id?:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/contracts/${contract_id}/run`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({dataset_id:dataset_id||null}) }), 'Exécution du data contract impossible');
}
export async function getContractRuns(token:string, workspace_id:string, contract_id?:string, dataset_id?:string) {
  const params=new URLSearchParams(); if(contract_id)params.set('contract_id',contract_id); if(dataset_id)params.set('dataset_id',dataset_id);
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/contract-runs?${params.toString()}`, { headers:enterpriseHeaders(token) }), 'Historique des contrats indisponible');
}
export async function getLineageGraph(token:string, workspace_id:string, dataset_id?:string) {
  const params=new URLSearchParams(); if(dataset_id)params.set('dataset_id',dataset_id);
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/lineage?${params.toString()}`, { headers:enterpriseHeaders(token) }), 'Lineage indisponible');
}
export async function getImpactAnalysis(token:string, workspace_id:string, resource_type:string, resource_id:string, depth=6) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/impact/${encodeURIComponent(resource_type)}/${encodeURIComponent(resource_id)}?depth=${depth}`, { headers:enterpriseHeaders(token) }), "Analyse d'impact indisponible");
}
export async function getPublicationGate(token:string, workspace_id:string, dataset_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/publication-gate`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({dataset_id}) }), 'Publication gate indisponible');
}

// ---------------------------- Operational Intelligence & AI Evaluation v2.9 ----------------------------
export async function getOperationalOverview(token:string, workspace_id:string, hours=24) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/operational/overview?hours=${hours}`, { headers:enterpriseHeaders(token) }), 'Observabilité opérationnelle indisponible');
}
export async function getOperationalUsage(token:string, workspace_id:string, hours=720) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/operational/usage?hours=${hours}`, { headers:enterpriseHeaders(token) }), 'Télémétrie d’usage indisponible');
}
export async function getOperationalTelemetry(token:string, workspace_id:string, hours=24, limit=100, event_kind?:string) {
  const p=new URLSearchParams({hours:String(hours),limit:String(limit)}); if(event_kind)p.set('event_kind',event_kind);
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/operational/telemetry?${p.toString()}`, { headers:enterpriseHeaders(token) }), 'Événements de télémétrie indisponibles');
}
export async function getJobAttempts(token:string, job_id:string) {
  return parse<any>(await apiFetch(`${API}/jobs/${job_id}/attempts`, { headers:enterpriseHeaders(token) }), 'Tentatives du job indisponibles');
}
export async function getEvaluationSuites(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/evaluations/suites`, { headers:enterpriseHeaders(token) }), "Suites d'évaluation indisponibles");
}
export async function createEvaluationSuite(token:string, workspace_id:string, payload:{dataset_id:string;name:string;description?:string}) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/evaluations/suites`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), "Création de la suite d'évaluation impossible");
}
export async function getEvaluationSuite(token:string, workspace_id:string, suite_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/evaluations/suites/${suite_id}`, { headers:enterpriseHeaders(token) }), "Suite d'évaluation indisponible");
}
export async function addEvaluationCase(token:string, workspace_id:string, suite_id:string, payload:{question:string;expectations:Record<string,unknown>}) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/evaluations/suites/${suite_id}/cases`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), "Ajout du cas d'évaluation impossible");
}
export async function runEvaluationSuite(token:string, workspace_id:string, suite_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/evaluations/suites/${suite_id}/run`, { method:'POST', headers:enterpriseHeaders(token) }), "Exécution de l'évaluation impossible");
}
export async function getEvaluationRun(token:string, workspace_id:string, run_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/evaluations/runs/${run_id}`, { headers:enterpriseHeaders(token) }), "Run d'évaluation indisponible");
}

// ---------------------------- Enterprise Action Connectors v2.11 ----------------------------
export async function getActionSummary(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/summary`, { headers:enterpriseHeaders(token) }), 'Synthèse des actions indisponible');
}
export async function getActionDestinations(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/destinations`, { headers:enterpriseHeaders(token) }), 'Destinations indisponibles');
}
export async function createActionDestination(token:string, workspace_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/destinations`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Création de la destination impossible');
}
export async function deleteActionDestination(token:string, workspace_id:string, destination_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/destinations/${destination_id}`, { method:'DELETE', headers:enterpriseHeaders(token) }), 'Suppression de la destination impossible');
}
export async function getActionRules(token:string, workspace_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/rules`, { headers:enterpriseHeaders(token) }), 'Règles d’automatisation indisponibles');
}
export async function saveActionRule(token:string, workspace_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/rules`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Enregistrement de la règle impossible');
}
export async function deleteActionRule(token:string, workspace_id:string, rule_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/rules/${rule_id}`, { method:'DELETE', headers:enterpriseHeaders(token) }), 'Suppression de la règle impossible');
}
export async function dispatchActionEvent(token:string, workspace_id:string, payload:Record<string,unknown>) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/events`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify(payload) }), 'Déclenchement de l’action impossible');
}
export async function getActionRuns(token:string, workspace_id:string, status?:string, limit=200) {
  const p=new URLSearchParams({limit:String(limit)}); if(status&&status!=='all')p.set('status',status);
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/runs?${p.toString()}`, { headers:enterpriseHeaders(token) }), 'Historique des actions indisponible');
}
export async function getActionRun(token:string, workspace_id:string, run_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/runs/${run_id}`, { headers:enterpriseHeaders(token) }), 'Détail de l’action indisponible');
}
export async function approveActionRun(token:string, workspace_id:string, run_id:string, note='') {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/runs/${run_id}/approve`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({note}) }), 'Approbation impossible');
}
export async function rejectActionRun(token:string, workspace_id:string, run_id:string, note='') {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/runs/${run_id}/reject`, { method:'POST', headers:enterpriseHeaders(token), body:JSON.stringify({note}) }), 'Rejet impossible');
}
export async function replayActionRun(token:string, workspace_id:string, run_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/runs/${run_id}/replay`, { method:'POST', headers:enterpriseHeaders(token) }), 'Replay impossible');
}

// ---------------------------- Enterprise Action Connectors v2.11 ----------------------------
export async function testActionDestination(token:string, workspace_id:string, destination_id:string) {
  return parse<any>(await apiFetch(`${API}/workspaces/${workspace_id}/actions/destinations/${destination_id}/test`, { method:'POST', headers:enterpriseHeaders(token) }), 'Test de la destination impossible');
}


export async function getModelEngines() {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/engines`),
    'Moteurs ML indisponibles',
  );
}

export async function runModelBenchmark(
  datasetId: string,
  payload: {
    target: string;
    task?: string;
    primary_metric?: string;
    cv_folds?: number;
    max_candidates?: number;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/${encodeURIComponent(datasetId)}/models/benchmark`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Benchmark de modèles impossible',
  );
}

export async function getModelXAICapabilities(modelId: string) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/xai/capabilities`),
    'Capacités XAI indisponibles',
  );
}

export async function runModelPDP(
  modelId: string,
  payload: {
    features: string[];
    grid_points?: number;
    class_label?: string | number | null;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/xai/pdp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Dépendance partielle impossible',
  );
}

export async function runModelSHAP(
  modelId: string,
  payload: {
    row?: Record<string, unknown> | null;
    max_rows?: number;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/xai/shap`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Calcul SHAP impossible',
  );
}

export async function runModelCounterfactuals(
  modelId: string,
  payload: {
    row: Record<string, unknown>;
    desired_class?: string | number | null;
    desired_value?: number | null;
    direction?: 'increase' | 'decrease' | null;
    max_changes?: number;
    max_results?: number;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/xai/counterfactuals`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Recherche contrefactuelle impossible',
  );
}


export async function runRootCauseAnalysis(
  datasetId: string,
  payload: {
    target: string;
    comparison_column: string;
    baseline_value?: string | number | boolean | null;
    current_value?: string | number | boolean | null;
    metric?: 'mean' | 'sum' | 'count';
    dimensions?: string[] | null;
    time_grain?: 'auto' | 'raw' | 'day' | 'week' | 'month' | 'quarter' | 'year';
    min_segment_size?: number;
    top_n?: number;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/${encodeURIComponent(datasetId)}/root-cause`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Analyse des causes impossible',
  );
}

export async function optimizeModelScenarios(
  modelId: string,
  payload: {
    base_row: Record<string, unknown>;
    controls: Record<string, {
      values?: unknown[];
      min?: number;
      max?: number;
      steps?: number;
    }>;
    objective?: 'maximize' | 'minimize' | 'target';
    target_value?: number | null;
    desired_class?: string | number | boolean | null;
    max_candidates?: number;
    max_results?: number;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/optimize-scenarios`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Optimisation des scénarios impossible',
  );
}

export async function runModelFairnessAudit(
  modelId: string,
  payload: {
    protected_columns: string[];
    positive_label?: string | number | boolean | null;
    mode?: 'separate' | 'intersectional' | 'both';
    min_group_size?: number;
    persist_summary?: boolean;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/responsible-ai/fairness`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Audit Responsible AI impossible',
  );
}

export async function runModelResponsibleAIGate(
  modelId: string,
  payload: {
    protected_columns: string[];
    positive_label?: string | number | boolean | null;
    mode?: 'separate' | 'intersectional' | 'both';
    min_group_size?: number;
    persist_summary?: boolean;
    policy?: Record<string, unknown>;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/responsible-ai/gate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Publication gate Responsible AI impossible',
  );
}

export async function runModelResponsibleAIRisk(
  modelId: string,
  payload: {
    protected_columns?: string[];
    positive_label?: string | number | boolean | null;
    mode?: 'separate' | 'intersectional' | 'both';
    min_group_size?: number;
    persist_summary?: boolean;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/responsible-ai/risk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Évaluation du risque modèle impossible',
  );
}

export async function runModelPopulationDrift(
  modelId: string,
  payload: {
    current_dataset_id: string;
    protected_columns: string[];
    positive_label?: string | number | boolean | null;
    mode?: 'separate' | 'intersectional' | 'both';
    min_group_size?: number;
    persist_summary?: boolean;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/responsible-ai/drift`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Monitoring de population impossible',
  );
}


export async function getModelRegistrySummary() {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/registry/summary`),
    'Résumé du Model Registry indisponible',
  );
}

export async function getModelRegistryEntries(params?: {
  dataset_id?: string;
  stage?: string;
  model_key?: string;
}) {
  const search = new URLSearchParams();
  if (params?.dataset_id) search.set('dataset_id', params.dataset_id);
  if (params?.stage) search.set('stage', params.stage);
  if (params?.model_key) search.set('model_key', params.model_key);
  const suffix = search.toString() ? `?${search.toString()}` : '';
  return parse<any>(
    await apiFetch(`${API}/datasets/models/registry/entries${suffix}`),
    'Model Registry indisponible',
  );
}

export async function registerModelInRegistry(
  modelId: string,
  payload: { name?: string | null; notes?: string },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/registry/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Enregistrement du modèle impossible',
  );
}

export async function getModelRegistryDetail(modelId: string) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/registry`),
    'Détail du Model Registry indisponible',
  );
}

export async function transitionModelStage(
  modelId: string,
  payload: { target_stage: 'draft' | 'staging' | 'production' | 'retired'; note?: string },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/registry/transition`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Transition du modèle impossible',
  );
}

export async function runModelMonitoring(
  modelId: string,
  payload: {
    current_dataset_id: string;
    policy?: Record<string, unknown> | null;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/monitor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Monitoring du modèle impossible',
  );
}

export async function getModelMonitoringHistory(modelId: string, limit = 100) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/monitoring?limit=${limit}`),
    'Historique de monitoring indisponible',
  );
}

export async function getModelRetrainingPolicy(modelId: string) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/retraining-policy`),
    'Politique de réentraînement indisponible',
  );
}

export async function saveModelRetrainingPolicy(
  modelId: string,
  payload: {
    enabled: boolean;
    min_rows: number;
    metric_degradation_threshold: number;
    feature_drift_threshold: number;
    cooldown_hours: number;
    auto_create_request: boolean;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/retraining-policy`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Enregistrement de la politique impossible',
  );
}

export async function checkModelRetraining(
  modelId: string,
  createRequest = true,
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/retraining/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ create_request: createRequest }),
    }),
    'Vérification du réentraînement impossible',
  );
}

export async function getModelRetrainingRequests(modelId: string) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/retraining/requests`),
    'Demandes de réentraînement indisponibles',
  );
}


export async function getModelMonitorSchedule(modelId: string) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/monitor-schedule`),
    'Planning de monitoring indisponible',
  );
}

export async function saveModelMonitorSchedule(
  modelId: string,
  payload: {
    current_dataset_id: string;
    enabled: boolean;
    interval_minutes: number;
    policy?: Record<string, unknown> | null;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/monitor-schedule`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Enregistrement du planning de monitoring impossible',
  );
}


export async function getFeatureSets(status?: string) {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : '';
  return parse<any>(
    await apiFetch(`${API}/datasets/feature-store${suffix}`),
    'Feature Store indisponible',
  );
}

export async function createFeatureSet(payload: {
  name: string;
  source_dataset_id: string;
  features: string[];
  entity_keys?: string[];
  event_time_column?: string | null;
  description?: string;
}) {
  return parse<any>(
    await apiFetch(`${API}/datasets/feature-store`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Création du Feature Set impossible',
  );
}

export async function setFeatureSetStatus(
  featureSetId: string,
  status: 'draft' | 'active' | 'archived',
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/feature-store/${encodeURIComponent(featureSetId)}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    }),
    'Mise à jour du Feature Set impossible',
  );
}

export async function materializeFeatureSet(
  featureSetId: string,
  sourceDatasetId?: string | null,
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/feature-store/${encodeURIComponent(featureSetId)}/materialize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_dataset_id: sourceDatasetId ?? null }),
    }),
    'Matérialisation du Feature Set impossible',
  );
}

export async function getModelFeatureContract(modelId: string) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/feature-contract`),
    'Feature Contract du modèle indisponible',
  );
}

export async function getModelDeployments() {
  return parse<any>(
    await apiFetch(`${API}/datasets/serving/deployments`),
    'Deployments indisponibles',
  );
}

export async function createModelDeployment(payload: {
  name: string;
  endpoint_key: string;
  primary_model_id: string;
  strategy?: 'champion' | 'shadow' | 'canary';
  secondary_model_id?: string | null;
  traffic_percent?: number;
  status?: 'active' | 'inactive';
}) {
  return parse<any>(
    await apiFetch(`${API}/datasets/serving/deployments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Création du deployment impossible',
  );
}

export async function updateModelDeployment(
  deploymentId: string,
  payload: {
    primary_model_id?: string;
    strategy?: 'champion' | 'shadow' | 'canary';
    secondary_model_id?: string | null;
    traffic_percent?: number;
    status?: 'active' | 'inactive';
    reason?: string;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/serving/deployments/${encodeURIComponent(deploymentId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Mise à jour du deployment impossible',
  );
}

export async function rollbackModelDeployment(deploymentId: string) {
  return parse<any>(
    await apiFetch(`${API}/datasets/serving/deployments/${encodeURIComponent(deploymentId)}/rollback`, {
      method: 'POST',
    }),
    'Rollback du deployment impossible',
  );
}

export async function getModelDeploymentMetrics(
  deploymentId: string,
  limit = 500,
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/serving/deployments/${encodeURIComponent(deploymentId)}/metrics?limit=${limit}`),
    'Métriques de serving indisponibles',
  );
}

export async function scoreModelDeployment(
  endpointKey: string,
  payload: {
    rows: Record<string, unknown>[];
    request_id?: string | null;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/serving/${encodeURIComponent(endpointKey)}/predict`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Scoring du deployment impossible',
  );
}

export async function batchScoreModel(
  modelId: string,
  payload: {
    dataset_id: string;
    prediction_column?: string;
    background?: boolean;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/models/${encodeURIComponent(modelId)}/batch-score`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Batch scoring impossible',
  );
}


export type AIAnalysisRunEvent = {
  id: string;
  status: 'queued' | 'running' | 'cancel_requested' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  stage?: string | null;
  current_tool?: string | null;
  cached?: boolean;
  error?: string | null;
  result?: any;
};

export async function startAIAnalysisRun(
  id: string,
  payload: {
    question: string;
    target?: string | null;
    date_column?: string | null;
    variables?: string[];
    group?: string | null;
    horizon?: number;
    mode?: 'auto' | 'fast' | 'deep';
    use_cache?: boolean;
  },
) {
  return parse<any>(
    await apiFetch(`${API}/datasets/${encodeURIComponent(id)}/ai/analyze/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
    'Démarrage AI Analyst impossible',
  );
}

export async function getAIAnalysisRun(id: string, runId: string) {
  return parse<any>(
    await apiFetch(`${API}/datasets/${encodeURIComponent(id)}/ai/runs/${encodeURIComponent(runId)}`),
    'Exécution AI Analyst introuvable',
  );
}

export async function cancelAIAnalysisRun(id: string, runId: string) {
  return parse<any>(
    await apiFetch(`${API}/datasets/${encodeURIComponent(id)}/ai/runs/${encodeURIComponent(runId)}/cancel`, {
      method: 'POST',
    }),
    'Annulation AI Analyst impossible',
  );
}

export async function streamAIAnalysisRun(
  id: string,
  runId: string,
  onEvent: (event: AIAnalysisRunEvent) => void,
  signal?: AbortSignal,
) {
  const response = await apiFetch(
    `${API}/datasets/${encodeURIComponent(id)}/ai/runs/${encodeURIComponent(runId)}/events`,
    { headers: { Accept: 'text/event-stream' }, signal },
  );
  if (!response.ok) {
    let detail = 'Flux AI Analyst indisponible';
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new Error(detail);
  }
  if (!response.body) throw new Error('Flux AI Analyst vide');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const packet = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const lines = packet.split('\n');
      const eventName = (lines.find(line => line.startsWith('event:'))?.slice(6).trim()) || 'message';
      const data = lines
        .filter(line => line.startsWith('data:'))
        .map(line => line.slice(5).trim())
        .join('\n');
      if (data && eventName === 'analysis') {
        onEvent(JSON.parse(data) as AIAnalysisRunEvent);
      }
      boundary = buffer.indexOf('\n\n');
    }
  }
}


export async function getCdcCompliance() {
  return parse<any>(
    await apiFetch(`${API}/system/cdc-compliance`),
    'Matrice CDC indisponible',
  );
}

export async function getProductionAcceptance() {
  return parse<any>(
    await apiFetch(`${API}/system/production-acceptance`),
    'Statut d’acceptation indisponible',
  );
}
