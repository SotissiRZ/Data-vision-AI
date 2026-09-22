"use client";

import { useEffect, useMemo, useState } from "react";

import {
  createAssistantProvider,
  deleteAssistantProvider,
  getAssistantSettings,
  saveAssistantSettings,
  testAssistantProvider,
  updateAssistantProvider,
  type AssistantAISettings,
  type AssistantProvider,
  type AssistantProviderInput,
  type AssistantSettingsSnapshot,
  type AssistantTask,
} from "../../lib/assistant/settings-client";

import styles from "./AIProviderControlCenter.module.css";

const TASKS: Array<{ key: AssistantTask; label: string; description: string }> = [
  { key: "planner", label: "Planner", description: "Comprendre l'objectif et construire un plan." },
  { key: "explanation", label: "Explication", description: "Répondre et expliquer les résultats." },
  { key: "critic", label: "Critic", description: "Relire les sorties et signaler les incohérences." },
  { key: "summarization", label: "Résumé", description: "Synthèses courtes et narration." },
];

const EMPTY_PROVIDER: AssistantProviderInput = {
  name: "Modèle local",
  provider_type: "ollama",
  location: "local",
  base_url: "http://host.docker.internal:11434",
  model: "",
  enabled: true,
  priority: 100,
  structured_output: true,
  max_context_tokens: null,
  secret_id: null,
  api_key_env: null,
  input_cost_per_million: null,
  output_cost_per_million: null,
};

export function AIProviderControlCenter({
  setError,
}: {
  setError: (message: string) => void;
}) {
  const [snapshot, setSnapshot] = useState<AssistantSettingsSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [providerDraft, setProviderDraft] =
    useState<AssistantProviderInput>(EMPTY_PROVIDER);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [providerFormOpen, setProviderFormOpen] = useState(false);
  const [testState, setTestState] = useState<
    Record<string, { busy?: boolean; ok?: boolean; text?: string }>
  >({});

  async function reload() {
    setLoading(true);
    try {
      setSnapshot(await getAssistantSettings());
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const providers = snapshot?.providers ?? [];
  const settings = snapshot?.settings;

  const enabledProviders = useMemo(
    () => providers.filter((provider) => provider.enabled),
    [providers],
  );

  function updateSettings(
    updater: (settings: AssistantAISettings) => AssistantAISettings,
  ) {
    setSnapshot((current) => {
      if (!current) return current;
      return {
        ...current,
        settings: updater({
          ...current.settings,
          task_routes: { ...current.settings.task_routes },
          fallback_order: [...current.settings.fallback_order],
          external_data_policy: {
            ...current.settings.external_data_policy,
          },
        }),
      };
    });
  }

  async function persistSettings() {
    if (!snapshot) return;
    setSaving(true);
    try {
      await saveAssistantSettings(snapshot.settings);
      await reload();
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  }

  function startCreate() {
    setEditingId(null);
    setProviderDraft(EMPTY_PROVIDER);
    setProviderFormOpen(true);
  }

  function startEdit(provider: AssistantProvider) {
    setEditingId(provider.id);
    setProviderDraft({
      name: provider.name,
      provider_type: provider.provider_type,
      location: provider.location,
      base_url: provider.base_url,
      model: provider.model,
      enabled: provider.enabled,
      priority: provider.priority,
      structured_output: provider.structured_output,
      max_context_tokens: provider.max_context_tokens ?? null,
      secret_id: provider.secret_id ?? null,
      api_key_env: provider.api_key_env ?? null,
      input_cost_per_million: provider.input_cost_per_million ?? null,
      output_cost_per_million: provider.output_cost_per_million ?? null,
    });
    setProviderFormOpen(true);
  }

  async function persistProvider() {
    setSaving(true);
    try {
      if (!providerDraft.model.trim()) {
        throw new Error("Le nom du modèle est obligatoire.");
      }

      if (editingId) {
        await updateAssistantProvider(editingId, providerDraft);
      } else {
        await createAssistantProvider(providerDraft);
      }
      setProviderFormOpen(false);
      setEditingId(null);
      setProviderDraft(EMPTY_PROVIDER);
      await reload();
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  }

  async function removeProvider(provider: AssistantProvider) {
    if (
      !window.confirm(
        `Supprimer le provider « ${provider.name} » ?\n\nAucun secret ne sera supprimé du Secret Vault.`,
      )
    ) {
      return;
    }
    try {
      await deleteAssistantProvider(provider.id);
      await reload();
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    }
  }

  async function testProvider(provider: AssistantProvider) {
    setTestState((current) => ({
      ...current,
      [provider.id]: { busy: true },
    }));

    try {
      const result = await testAssistantProvider(provider.id);
      setTestState((current) => ({
        ...current,
        [provider.id]: {
          ok: true,
          text: `OK · ${result.latency_ms} ms · ${result.model}`,
        },
      }));
    } catch (error) {
      setTestState((current) => ({
        ...current,
        [provider.id]: {
          ok: false,
          text: error instanceof Error ? error.message : String(error),
        },
      }));
    }
  }

  function moveFallback(providerId: string, direction: -1 | 1) {
    updateSettings((current) => {
      const order = current.fallback_order.length
        ? [...current.fallback_order]
        : enabledProviders.map((provider) => provider.id);
      const index = order.indexOf(providerId);
      if (index < 0) return current;
      const target = index + direction;
      if (target < 0 || target >= order.length) return current;
      [order[index], order[target]] = [order[target], order[index]];
      return { ...current, fallback_order: order };
    });
  }

  if (loading && !snapshot) {
    return (
      <div className={styles.page}>
        <div className={styles.loading}>Chargement du Control Center IA…</div>
      </div>
    );
  }

  if (!snapshot || !settings) {
    return null;
  }

  const usage = snapshot.usage;
  const budget = settings.monthly_budget_usd;
  const budgetPct =
    budget > 0
      ? Math.min(100, (usage.estimated_cost_usd / budget) * 100)
      : 0;

  const fallbackOrder = settings.fallback_order.length
    ? settings.fallback_order
        .map((id) => providers.find((provider) => provider.id === id))
        .filter((provider): provider is AssistantProvider => Boolean(provider))
    : enabledProviders;

  return (
    <div className={styles.page}>
      <div className={styles.pageTitle}>
        <div>
          <span className={styles.eyebrow}>GOUVERNER · IA & MODÈLES</span>
          <h1>AI Control Center</h1>
          <p>
            Configurez les modèles, la confidentialité, le routage et les budgets.
            Les modèles planifient et expliquent ; les moteurs DataVision restent
            responsables des calculs et des actions.
          </p>
        </div>
        <button
          type="button"
          className={styles.primary}
          onClick={() => void persistSettings()}
          disabled={saving}
        >
          {saving ? "Enregistrement…" : "Enregistrer"}
        </button>
      </div>

      <div className={styles.metrics}>
        <Metric label="Contexte" value={snapshot.scope.type === "local" ? "Local" : "Workspace"} />
        <Metric label="Providers actifs" value={String(enabledProviders.length)} />
        <Metric label="Appels ce mois" value={String(usage.calls)} />
        <Metric
          label="Coût estimé"
          value={`${usage.estimated_cost_usd.toFixed(4)} USD`}
        />
      </div>

      <div className={styles.gridTwo}>
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <h3>Politique IA</h3>
              <p>Contrôle du planner, de la confidentialité et du fallback.</p>
            </div>
          </div>

          <div className={styles.formGrid}>
            <Field label="Mode du planner">
              <select
                value={settings.planner_mode}
                onChange={(event) =>
                  updateSettings((current) => ({
                    ...current,
                    planner_mode: event.target.value as "deterministic" | "gateway",
                  }))
                }
              >
                <option value="deterministic">Déterministe uniquement</option>
                <option value="gateway">Model Gateway + garde-fous</option>
              </select>
            </Field>

            <Field label="Confidentialité">
              <select
                value={settings.privacy_mode}
                onChange={(event) => {
                  const privacy = event.target.value as AssistantAISettings["privacy_mode"];
                  updateSettings((current) => ({
                    ...current,
                    privacy_mode: privacy,
                    allow_external_ai:
                      privacy === "local_only"
                        ? false
                        : current.allow_external_ai,
                  }));
                }}
              >
                <option value="local_only">Local uniquement</option>
                <option value="prefer_local">Préférer le local</option>
                <option value="allow_external">Autoriser l'externe</option>
              </select>
            </Field>

            <Field label="Budget mensuel externe (USD)">
              <input
                type="number"
                min="0"
                step="0.5"
                value={settings.monthly_budget_usd}
                onChange={(event) =>
                  updateSettings((current) => ({
                    ...current,
                    monthly_budget_usd: Number(event.target.value || 0),
                  }))
                }
              />
            </Field>

            <Field label="Événements récents transmis">
              <input
                type="number"
                min="0"
                max="50"
                value={settings.external_data_policy.max_recent_events}
                onChange={(event) =>
                  updateSettings((current) => ({
                    ...current,
                    external_data_policy: {
                      ...current.external_data_policy,
                      max_recent_events: Number(event.target.value || 0),
                    },
                  }))
                }
              />
            </Field>
          </div>

          <div className={styles.checks}>
            <Check
              checked={settings.allow_external_ai}
              disabled={settings.privacy_mode === "local_only"}
              label="Autoriser explicitement les providers externes"
              onChange={(checked) =>
                updateSettings((current) => ({
                  ...current,
                  allow_external_ai:
                    current.privacy_mode === "local_only" ? false : checked,
                }))
              }
            />
            <Check
              checked={settings.allow_provider_fallback}
              label="Autoriser le fallback entre providers"
              onChange={(checked) =>
                updateSettings((current) => ({
                  ...current,
                  allow_provider_fallback: checked,
                }))
              }
            />
            <Check
              checked={settings.fallback_to_deterministic}
              label="Revenir au planner déterministe si l'IA échoue"
              onChange={(checked) =>
                updateSettings((current) => ({
                  ...current,
                  fallback_to_deterministic: checked,
                }))
              }
            />
            <Check
              checked={settings.external_data_policy.include_column_names}
              label="Autoriser les noms de colonnes vers un provider externe"
              onChange={(checked) =>
                updateSettings((current) => ({
                  ...current,
                  external_data_policy: {
                    ...current.external_data_policy,
                    include_column_names: checked,
                  },
                }))
              }
            />
            <Check
              checked={settings.deny_external_when_cost_unknown}
              label="Bloquer l'externe si le coût du modèle est inconnu"
              onChange={(checked) =>
                updateSettings((current) => ({
                  ...current,
                  deny_external_when_cost_unknown: checked,
                }))
              }
            />
          </div>

          <div className={styles.privacyNote}>
            <strong>Invariant :</strong> les lignes brutes et les valeurs
            d'échantillon ne sont jamais envoyées par cette couche. Le schéma du
            dataset peut être transmis selon la politique ci-dessus.
          </div>
        </section>

        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <div>
              <h3>Budget & consommation</h3>
              <p>Télémétrie agrégée du mois courant.</p>
            </div>
          </div>

          <div className={styles.usageList}>
            <Usage label="Tokens entrée" value={usage.input_tokens.toLocaleString("fr-FR")} />
            <Usage label="Tokens sortie" value={usage.output_tokens.toLocaleString("fr-FR")} />
            <Usage label="Appels coût inconnu" value={String(usage.unknown_cost_calls)} />
            <Usage label="Coût estimé" value={`${usage.estimated_cost_usd.toFixed(6)} USD`} />
          </div>

          <div className={styles.budgetBar}>
            <div>
              <span>Budget utilisé</span>
              <strong>
                {budget > 0
                  ? `${budgetPct.toFixed(1)} %`
                  : "Budget non limité"}
              </strong>
            </div>
            <div className={styles.track}>
              <span style={{ width: `${budget > 0 ? budgetPct : 0}%` }} />
            </div>
          </div>
        </section>
      </div>

      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <div>
            <h3>Routage par tâche</h3>
            <p>Chaque rôle IA peut utiliser un provider différent.</p>
          </div>
        </div>

        <div className={styles.routes}>
          {TASKS.map((task) => {
            const route = snapshot.routes[task.key];
            return (
              <div key={task.key} className={styles.routeCard}>
                <div>
                  <strong>{task.label}</strong>
                  <p>{task.description}</p>
                </div>

                <select
                  value={settings.task_routes[task.key] ?? ""}
                  onChange={(event) =>
                    updateSettings((current) => ({
                      ...current,
                      task_routes: {
                        ...current.task_routes,
                        [task.key]: event.target.value || null,
                      },
                    }))
                  }
                >
                  <option value="">Automatique</option>
                  {providers.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.name} · {provider.model}
                    </option>
                  ))}
                </select>

                <div className={styles.routePreview}>
                  {route?.selected_provider_id
                    ? `→ ${
                        providers.find(
                          (provider) =>
                            provider.id === route.selected_provider_id,
                        )?.name ?? route.selected_provider_id
                      }`
                    : settings.planner_mode === "deterministic" &&
                        task.key === "planner"
                      ? "→ Planner déterministe"
                      : "→ Aucun provider éligible"}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <div>
            <h3>Ordre de secours</h3>
            <p>
              Utilisé uniquement lorsque le fallback est autorisé et respecte
              toujours la politique de confidentialité.
            </p>
          </div>
        </div>

        {fallbackOrder.length ? (
          <div className={styles.fallbackList}>
            {fallbackOrder.map((provider, index) => (
              <div key={provider.id} className={styles.fallbackItem}>
                <span>{index + 1}</span>
                <div>
                  <strong>{provider.name}</strong>
                  <small>
                    {provider.location} · {provider.model}
                  </small>
                </div>
                <div className={styles.fallbackButtons}>
                  <button
                    type="button"
                    disabled={index === 0}
                    onClick={() => moveFallback(provider.id, -1)}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    disabled={index === fallbackOrder.length - 1}
                    onClick={() => moveFallback(provider.id, 1)}
                  >
                    ↓
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className={styles.empty}>Aucun provider actif.</div>
        )}
      </section>

      <section className={styles.panel}>
        <div className={styles.panelHeader}>
          <div>
            <h3>Providers</h3>
            <p>Local, on-premise ou API externe explicitement autorisée.</p>
          </div>
          <button type="button" className={styles.primary} onClick={startCreate}>
            + Ajouter un provider
          </button>
        </div>

        {providers.length ? (
          <div className={styles.providerGrid}>
            {providers.map((provider) => {
              const test = testState[provider.id];
              return (
                <article key={provider.id} className={styles.providerCard}>
                  <div className={styles.providerHead}>
                    <div>
                      <span
                        className={`${styles.statusDot} ${
                          provider.enabled ? styles.enabled : styles.disabled
                        }`}
                      />
                      <strong>{provider.name}</strong>
                    </div>
                    <span className={styles.providerKind}>
                      {provider.location}
                    </span>
                  </div>

                  <dl>
                    <div>
                      <dt>Type</dt>
                      <dd>{provider.provider_type}</dd>
                    </div>
                    <div>
                      <dt>Modèle</dt>
                      <dd>{provider.model}</dd>
                    </div>
                    <div>
                      <dt>Endpoint</dt>
                      <dd title={provider.base_url}>{provider.base_url}</dd>
                    </div>
                    <div>
                      <dt>Priorité</dt>
                      <dd>{provider.priority}</dd>
                    </div>
                  </dl>

                  {test && (
                    <div
                      className={`${styles.testResult} ${
                        test.ok === false ? styles.testFail : ""
                      }`}
                    >
                      {test.busy ? "Test en cours…" : test.text}
                    </div>
                  )}

                  <div className={styles.providerActions}>
                    <button
                      type="button"
                      onClick={() => void testProvider(provider)}
                      disabled={test?.busy}
                    >
                      Tester
                    </button>
                    <button type="button" onClick={() => startEdit(provider)}>
                      Modifier
                    </button>
                    <button
                      type="button"
                      className={styles.danger}
                      onClick={() => void removeProvider(provider)}
                    >
                      Supprimer
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className={styles.empty}>
            Aucun provider configuré. Le planner déterministe continue de
            fonctionner sans modèle externe.
          </div>
        )}
      </section>

      {providerFormOpen && (
        <div
          className={styles.modalBackdrop}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setProviderFormOpen(false);
            }
          }}
        >
          <div className={styles.modal}>
            <div className={styles.modalHeader}>
              <div>
                <span className={styles.eyebrow}>MODEL PROVIDER</span>
                <h2>{editingId ? "Modifier le provider" : "Nouveau provider"}</h2>
              </div>
              <button
                type="button"
                onClick={() => setProviderFormOpen(false)}
              >
                ×
              </button>
            </div>

            <div className={styles.formGrid}>
              <Field label="Nom">
                <input
                  value={providerDraft.name}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      name: event.target.value,
                    }))
                  }
                />
              </Field>

              <Field label="Type">
                <select
                  value={providerDraft.provider_type}
                  onChange={(event) => {
                    const providerType = event.target.value as
                      | "ollama"
                      | "openai_compatible"
                      | "anthropic"
                      | "gemini";
                    const defaults =
                      providerType === "anthropic"
                        ? { location: "external" as const, base_url: "https://api.anthropic.com", name: "Anthropic" }
                        : providerType === "gemini"
                          ? { location: "external" as const, base_url: "https://generativelanguage.googleapis.com/v1beta", name: "Gemini" }
                          : providerType === "ollama"
                            ? { location: "local" as const, base_url: "http://host.docker.internal:11434", name: "Modèle local" }
                            : { location: current.location, base_url: current.base_url, name: current.name };
                    setProviderDraft((current) => ({
                      ...current,
                      provider_type: providerType,
                      ...defaults,
                    }));
                  }}
                >
                  <option value="ollama">Ollama / local compatible</option>
                  <option value="openai_compatible">
                    API OpenAI-compatible
                  </option>
                  <option value="anthropic">Anthropic natif</option>
                  <option value="gemini">Google Gemini natif</option>
                </select>
              </Field>

              <Field label="Localisation">
                <select
                  value={providerDraft.location}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      location: event.target.value as "local" | "external",
                    }))
                  }
                >
                  <option value="local">Local / on-premise</option>
                  <option value="external">Externe</option>
                </select>
              </Field>

              <Field label="Modèle">
                <input
                  placeholder="ex. llama3.2, claude-…, gemini-…"
                  value={providerDraft.model}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      model: event.target.value,
                    }))
                  }
                />
              </Field>

              <Field label="Base URL">
                <input
                  value={providerDraft.base_url}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      base_url: event.target.value,
                    }))
                  }
                />
              </Field>

              <Field label="Priorité">
                <input
                  type="number"
                  min="1"
                  value={providerDraft.priority}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      priority: Number(event.target.value || 100),
                    }))
                  }
                />
              </Field>

              {snapshot.scope.type === "workspace" ? (
                <Field label="Secret Vault ID">
                  <input
                    placeholder="ID du secret créé dans Identité & Secrets"
                    value={providerDraft.secret_id ?? ""}
                    onChange={(event) =>
                      setProviderDraft((current) => ({
                        ...current,
                        secret_id: event.target.value || null,
                        api_key_env: null,
                      }))
                    }
                  />
                </Field>
              ) : (
                <Field label="Variable d'environnement API key">
                  <input
                    placeholder="ex. MY_MODEL_API_KEY"
                    value={providerDraft.api_key_env ?? ""}
                    onChange={(event) =>
                      setProviderDraft((current) => ({
                        ...current,
                        api_key_env: event.target.value || null,
                        secret_id: null,
                      }))
                    }
                  />
                </Field>
              )}

              <Field label="Coût entrée / 1M tokens">
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={providerDraft.input_cost_per_million ?? ""}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      input_cost_per_million:
                        event.target.value === ""
                          ? null
                          : Number(event.target.value),
                    }))
                  }
                />
              </Field>

              <Field label="Coût sortie / 1M tokens">
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={providerDraft.output_cost_per_million ?? ""}
                  onChange={(event) =>
                    setProviderDraft((current) => ({
                      ...current,
                      output_cost_per_million:
                        event.target.value === ""
                          ? null
                          : Number(event.target.value),
                    }))
                  }
                />
              </Field>
            </div>

            <div className={styles.checks}>
              <Check
                checked={providerDraft.enabled}
                label="Provider actif"
                onChange={(checked) =>
                  setProviderDraft((current) => ({
                    ...current,
                    enabled: checked,
                  }))
                }
              />
              <Check
                checked={providerDraft.structured_output}
                label="Supporte les sorties structurées"
                onChange={(checked) =>
                  setProviderDraft((current) => ({
                    ...current,
                    structured_output: checked,
                  }))
                }
              />
            </div>

            <div className={styles.modalNote}>
              Les secrets ne sont jamais enregistrés ici. En Entreprise,
              référencez un secret du module <b>Identité & Secrets</b>.
            </div>

            <div className={styles.modalActions}>
              <button
                type="button"
                onClick={() => setProviderFormOpen(false)}
              >
                Annuler
              </button>
              <button
                type="button"
                className={styles.primary}
                onClick={() => void persistProvider()}
                disabled={saving}
              >
                {saving ? "Enregistrement…" : "Enregistrer le provider"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className={styles.metric}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className={styles.field}>
      <span>{label}</span>
      {children}
    </label>
  );
}

function Check({
  checked,
  label,
  onChange,
  disabled = false,
}: {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className={styles.check}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>{label}</span>
    </label>
  );
}

function Usage({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className={styles.usageRow}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
