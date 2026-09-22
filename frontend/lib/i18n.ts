export type Locale = 'fr' | 'en' | 'es' | 'ar';

export const DEFAULT_LOCALE: Locale = 'fr';

export const LOCALES: ReadonlyArray<{code: Locale; label: string; nativeLabel: string; dir: 'ltr'|'rtl'}> = [
  {code:'fr', label:'French', nativeLabel:'Français', dir:'ltr'},
  {code:'en', label:'English', nativeLabel:'English', dir:'ltr'},
  {code:'es', label:'Spanish', nativeLabel:'Español', dir:'ltr'},
  {code:'ar', label:'Arabic', nativeLabel:'العربية', dir:'rtl'},
];

const fr: Record<string,string> = {
  'app.tagline':'Intelligence analytique vérifiable',
  'shell.local':'Local',
  'shell.noDataset':'Aucun dataset actif',
  'shell.quality':'Qualité',
  'shell.workspace':'WORKSPACE',
  'shell.localAnalysis':'Analyse locale',
  'shell.goalWorkflow':'Workflow orienté objectifs',
  'shell.import':'Importer des données',
  'shell.importing':'Analyse en cours…',
  'shell.activeContext':'CONTEXTE ACTIF',
  'shell.semantic':'Sémantique',
  'shell.trust':'Trust',
  'shell.settings':'Ouvrir les paramètres',
  'shell.search':'Rechercher dans DataVision…',
  'display.open':'Régler l’affichage, la langue et l’accessibilité',
  'display.title':'Affichage & accessibilité',
  'display.subtitle':'Préférences mémorisées et synchronisées',
  'display.close':'Fermer les réglages',
  'display.readingMode':'Mode de lecture',
  'display.normal':'Normal',
  'display.comfortable':'Confort',
  'display.large':'Grand texte',
  'display.zoom':'Zoom UI',
  'display.resetZoom':'Réinitialiser le zoom à 100 %',
  'display.language':'Langue',
  'display.highContrast':'Contraste renforcé',
  'display.reduceMotion':'Réduire les animations',
  'display.footnote':'Ces réglages agissent sur toute l’interface et sont synchronisés avec votre profil Entreprise.',
  'a11y.skipToContent':'Aller au contenu principal',
  'a11y.mainContent':'Contenu principal DataVision',
  'a11y.primaryNavigation':'Navigation principale',
  'a11y.contextNavigation':'Navigation de la section',
  'a11y.viewChanged':'Vue active : {view}',
  'error.title':'Erreur',
  'command.placeholder':'Rechercher un module ou poser une question aux données…',
  'command.navigation':'NAVIGATION',
  'command.analysis':'ANALYSE',
  'command.ask':'Demander à AI Analyst',
  'command.close':'Fermer',
  'area.overview':'Vue d’ensemble',
  'area.data':'Données',
  'area.analyze':'Analyser',
  'area.model':'Modéliser',
  'area.decide':'Décider',
  'area.publish':'Publier',
  'area.collaborate':'Collaborer',
  'area.governance':'Gouverner',
  'area.overview.description':'Synthèse & insights',
  'area.data.description':'Préparer & comprendre',
  'area.analyze.description':'Explorer & tester',
  'area.model.description':'Prédire & expliquer',
  'area.decide.description':'Sémantique & décisions',
  'area.publish.description':'Dashboards & rapports',
  'area.collaborate.description':'Revue & approbation',
  'area.governance.description':'Fiabilité, sources, SLO & sécurité',
  'view.home':'Vue d’ensemble', 'view.data':'Aperçu des données', 'view.quality':'Qualité', 'view.prepare':'Préparation', 'view.stats':'Statistiques descriptives',
  'view.visual':'Visualisation', 'view.tests':'Tests & corrélations', 'view.sql':'SQL', 'view.notebook':'Notebook', 'view.regression':'Régression', 'view.anova':'ANOVA', 'view.pca':'ACP', 'view.cluster':'Clustering',
  'view.model':'AutoML', 'view.registry':'Model Registry', 'view.serving':'Feature Store & Serving', 'view.forecast':'Forecasting', 'view.anomaly':'Anomalies', 'view.xai':'XAI', 'view.responsible':'Responsible AI', 'view.predict':'Prédictions',
  'view.insights':'Insights', 'view.inbox':'Inbox analytique', 'view.ai':'AI Analyst', 'view.semantic':'Couche sémantique', 'view.decision':'Decision Lab', 'view.actions':'Actions & Automation', 'view.trust':'Trust Center',
  'view.dashboard':'Dashboards', 'view.report':'Rapports', 'view.review':'Review Center', 'view.reliability':'Fiabilité & Lineage', 'view.sources':'Sources & Refresh', 'view.operations':'Observabilité & Eval',
  'view.identity':'Identité & Secrets', 'view.plugins':'Plugins & MCP', 'view.ai-settings':'IA & Modèles', 'view.compliance':'CDC & Acceptance', 'view.governance':'Gouvernance',
};

const en: Record<string,string> = {
  'app.tagline':'Verifiable analytics intelligence', 'shell.local':'Local', 'shell.noDataset':'No active dataset', 'shell.quality':'Quality',
  'shell.workspace':'WORKSPACE', 'shell.localAnalysis':'Local analysis', 'shell.goalWorkflow':'Goal-oriented workflow', 'shell.import':'Import data', 'shell.importing':'Analyzing…',
  'shell.activeContext':'ACTIVE CONTEXT', 'shell.semantic':'Semantic', 'shell.trust':'Trust', 'shell.settings':'Open settings', 'shell.search':'Search DataVision…',
  'display.open':'Adjust display, language and accessibility', 'display.title':'Display & accessibility', 'display.subtitle':'Saved and synchronized preferences', 'display.close':'Close settings',
  'display.readingMode':'Reading mode', 'display.normal':'Normal', 'display.comfortable':'Comfort', 'display.large':'Large text', 'display.zoom':'UI zoom', 'display.resetZoom':'Reset zoom to 100%',
  'display.language':'Language', 'display.highContrast':'High contrast', 'display.reduceMotion':'Reduce motion', 'display.footnote':'These settings apply across the interface and sync with your Enterprise profile.',
  'a11y.skipToContent':'Skip to main content', 'a11y.mainContent':'DataVision main content', 'a11y.primaryNavigation':'Primary navigation', 'a11y.contextNavigation':'Section navigation', 'a11y.viewChanged':'Active view: {view}',
  'error.title':'Error', 'command.placeholder':'Search a module or ask a question about your data…', 'command.navigation':'NAVIGATION', 'command.analysis':'ANALYSIS', 'command.ask':'Ask AI Analyst', 'command.close':'Close',
  'area.overview':'Overview','area.data':'Data','area.analyze':'Analyze','area.model':'Model','area.decide':'Decide','area.publish':'Publish','area.collaborate':'Collaborate','area.governance':'Govern',
  'area.overview.description':'Summary & insights','area.data.description':'Prepare & understand','area.analyze.description':'Explore & test','area.model.description':'Predict & explain','area.decide.description':'Semantic & decisions','area.publish.description':'Dashboards & reports','area.collaborate.description':'Review & approval','area.governance.description':'Reliability, sources, SLO & security',
  'view.home':'Overview','view.data':'Data preview','view.quality':'Quality','view.prepare':'Preparation','view.stats':'Descriptive statistics','view.visual':'Visualization','view.tests':'Tests & correlations','view.sql':'SQL','view.notebook':'Notebook','view.regression':'Regression','view.anova':'ANOVA','view.pca':'PCA','view.cluster':'Clustering','view.model':'AutoML','view.registry':'Model Registry','view.serving':'Feature Store & Serving','view.forecast':'Forecasting','view.anomaly':'Anomalies','view.xai':'XAI','view.responsible':'Responsible AI','view.predict':'Predictions','view.insights':'Insights','view.inbox':'Analytics Inbox','view.ai':'AI Analyst','view.semantic':'Semantic layer','view.decision':'Decision Lab','view.actions':'Actions & Automation','view.trust':'Trust Center','view.dashboard':'Dashboards','view.report':'Reports','view.review':'Review Center','view.reliability':'Reliability & Lineage','view.sources':'Sources & Refresh','view.operations':'Observability & Eval','view.identity':'Identity & Secrets','view.plugins':'Plugins & MCP','view.ai-settings':'AI & Models','view.compliance':'CDC & Acceptance','view.governance':'Governance',
};

const es: Record<string,string> = {
  'app.tagline':'Inteligencia analítica verificable', 'shell.local':'Local', 'shell.noDataset':'Ningún dataset activo', 'shell.quality':'Calidad', 'shell.workspace':'ESPACIO DE TRABAJO',
  'shell.localAnalysis':'Análisis local','shell.goalWorkflow':'Flujo orientado a objetivos','shell.import':'Importar datos','shell.importing':'Analizando…','shell.activeContext':'CONTEXTO ACTIVO','shell.semantic':'Semántica','shell.trust':'Confianza','shell.settings':'Abrir configuración','shell.search':'Buscar en DataVision…',
  'display.open':'Ajustar visualización, idioma y accesibilidad','display.title':'Visualización y accesibilidad','display.subtitle':'Preferencias guardadas y sincronizadas','display.close':'Cerrar configuración','display.readingMode':'Modo de lectura','display.normal':'Normal','display.comfortable':'Cómodo','display.large':'Texto grande','display.zoom':'Zoom de interfaz','display.resetZoom':'Restablecer zoom al 100 %','display.language':'Idioma','display.highContrast':'Alto contraste','display.reduceMotion':'Reducir animaciones','display.footnote':'Estos ajustes se aplican a toda la interfaz y se sincronizan con tu perfil Enterprise.',
  'a11y.skipToContent':'Ir al contenido principal','a11y.mainContent':'Contenido principal de DataVision','a11y.primaryNavigation':'Navegación principal','a11y.contextNavigation':'Navegación de sección','a11y.viewChanged':'Vista activa: {view}',
  'error.title':'Error','command.placeholder':'Buscar un módulo o preguntar sobre tus datos…','command.navigation':'NAVEGACIÓN','command.analysis':'ANÁLISIS','command.ask':'Preguntar a AI Analyst','command.close':'Cerrar',
  'area.overview':'Resumen','area.data':'Datos','area.analyze':'Analizar','area.model':'Modelar','area.decide':'Decidir','area.publish':'Publicar','area.collaborate':'Colaborar','area.governance':'Gobernar',
  'area.overview.description':'Resumen e insights','area.data.description':'Preparar y comprender','area.analyze.description':'Explorar y probar','area.model.description':'Predecir y explicar','area.decide.description':'Semántica y decisiones','area.publish.description':'Dashboards e informes','area.collaborate.description':'Revisión y aprobación','area.governance.description':'Fiabilidad, fuentes, SLO y seguridad',
  'view.home':'Resumen','view.data':'Vista de datos','view.quality':'Calidad','view.prepare':'Preparación','view.stats':'Estadísticas descriptivas','view.visual':'Visualización','view.tests':'Pruebas y correlaciones','view.sql':'SQL','view.notebook':'Notebook','view.regression':'Regresión','view.anova':'ANOVA','view.pca':'ACP','view.cluster':'Clustering','view.model':'AutoML','view.registry':'Model Registry','view.serving':'Feature Store & Serving','view.forecast':'Pronóstico','view.anomaly':'Anomalías','view.xai':'XAI','view.responsible':'IA responsable','view.predict':'Predicciones','view.insights':'Insights','view.inbox':'Bandeja analítica','view.ai':'AI Analyst','view.semantic':'Capa semántica','view.decision':'Decision Lab','view.actions':'Acciones y automatización','view.trust':'Trust Center','view.dashboard':'Dashboards','view.report':'Informes','view.review':'Review Center','view.reliability':'Fiabilidad y linaje','view.sources':'Fuentes y actualización','view.operations':'Observabilidad y evaluación','view.identity':'Identidad y secretos','view.plugins':'Plugins & MCP','view.ai-settings':'IA y modelos','view.compliance':'CDC y aceptación','view.governance':'Gobernanza',
};

const ar: Record<string,string> = {
  'app.tagline':'ذكاء تحليلي قابل للتحقق','shell.local':'محلي','shell.noDataset':'لا توجد مجموعة بيانات نشطة','shell.quality':'الجودة','shell.workspace':'مساحة العمل','shell.localAnalysis':'تحليل محلي','shell.goalWorkflow':'سير عمل موجّه بالأهداف','shell.import':'استيراد البيانات','shell.importing':'جارٍ التحليل…','shell.activeContext':'السياق النشط','shell.semantic':'الدلالات','shell.trust':'الثقة','shell.settings':'فتح الإعدادات','shell.search':'البحث في DataVision…',
  'display.open':'ضبط العرض واللغة وإمكانية الوصول','display.title':'العرض وإمكانية الوصول','display.subtitle':'تفضيلات محفوظة ومتزامنة','display.close':'إغلاق الإعدادات','display.readingMode':'وضع القراءة','display.normal':'عادي','display.comfortable':'مريح','display.large':'نص كبير','display.zoom':'تكبير الواجهة','display.resetZoom':'إعادة التكبير إلى 100٪','display.language':'اللغة','display.highContrast':'تباين عالٍ','display.reduceMotion':'تقليل الحركة','display.footnote':'تطبق هذه الإعدادات على الواجهة وتتم مزامنتها مع ملف Enterprise.',
  'a11y.skipToContent':'الانتقال إلى المحتوى الرئيسي','a11y.mainContent':'المحتوى الرئيسي لـ DataVision','a11y.primaryNavigation':'التنقل الرئيسي','a11y.contextNavigation':'تنقل القسم','a11y.viewChanged':'العرض النشط: {view}',
  'error.title':'خطأ','command.placeholder':'ابحث عن وحدة أو اسأل عن بياناتك…','command.navigation':'التنقل','command.analysis':'التحليل','command.ask':'اسأل AI Analyst','command.close':'إغلاق',
  'area.overview':'نظرة عامة','area.data':'البيانات','area.analyze':'تحليل','area.model':'نمذجة','area.decide':'قرار','area.publish':'نشر','area.collaborate':'تعاون','area.governance':'حوكمة',
  'area.overview.description':'ملخص ورؤى','area.data.description':'إعداد وفهم','area.analyze.description':'استكشاف واختبار','area.model.description':'تنبؤ وتفسير','area.decide.description':'دلالات وقرارات','area.publish.description':'لوحات وتقارير','area.collaborate.description':'مراجعة وموافقة','area.governance.description':'الموثوقية والمصادر وSLO والأمان',
  'view.home':'نظرة عامة','view.data':'معاينة البيانات','view.quality':'الجودة','view.prepare':'الإعداد','view.stats':'إحصاءات وصفية','view.visual':'التصور','view.tests':'الاختبارات والارتباطات','view.sql':'SQL','view.notebook':'دفتر العمل','view.regression':'الانحدار','view.anova':'ANOVA','view.pca':'PCA','view.cluster':'التجميع','view.model':'AutoML','view.registry':'سجل النماذج','view.serving':'Feature Store & Serving','view.forecast':'التنبؤ','view.anomaly':'الشذوذ','view.xai':'XAI','view.responsible':'الذكاء الاصطناعي المسؤول','view.predict':'التنبؤات','view.insights':'الرؤى','view.inbox':'صندوق التحليلات','view.ai':'AI Analyst','view.semantic':'الطبقة الدلالية','view.decision':'Decision Lab','view.actions':'الإجراءات والأتمتة','view.trust':'مركز الثقة','view.dashboard':'لوحات المعلومات','view.report':'التقارير','view.review':'مركز المراجعة','view.reliability':'الموثوقية والنسب','view.sources':'المصادر والتحديث','view.operations':'الرصد والتقييم','view.identity':'الهوية والأسرار','view.plugins':'Plugins & MCP','view.ai-settings':'الذكاء الاصطناعي والنماذج','view.compliance':'CDC والقبول','view.governance':'الحوكمة',
};

const dictionaries: Record<Locale,Record<string,string>> = {fr,en,es:{...fr,...es},ar:{...fr,...ar}};

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && LOCALES.some(item=>item.code===value);
}

export function localeDirection(locale: Locale): 'ltr'|'rtl' {
  return LOCALES.find(item=>item.code===locale)?.dir ?? 'ltr';
}

export function translate(locale: Locale, key: string, fallback?: string, params?: Record<string,string|number>): string {
  let value=dictionaries[locale]?.[key] ?? fr[key] ?? fallback ?? key;
  if(params){
    for(const [name,replacement] of Object.entries(params)){
      value=value.replaceAll(`{${name}}`,String(replacement));
    }
  }
  return value;
}

export function browserLocale(): Locale {
  if(typeof navigator==='undefined') return DEFAULT_LOCALE;
  const language=(navigator.language||DEFAULT_LOCALE).toLowerCase().split('-')[0];
  return isLocale(language)?language:DEFAULT_LOCALE;
}

export function numberLocale(locale: Locale): string {
  return locale==='fr'?'fr-FR':locale==='es'?'es-ES':locale==='ar'?'ar-MA':'en-US';
}
