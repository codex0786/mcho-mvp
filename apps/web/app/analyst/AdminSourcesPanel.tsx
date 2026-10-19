"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { apiRequest } from "../../lib/oidc";

type Source = {
  id: string;
  name: string;
  source_type: string;
  access_mode: string;
  license_status: string;
  homepage_url: string | null;
  license_terms_url: string | null;
  owner_name: string | null;
  retention_policy: string | null;
  refresh_cadence: string;
  terms_reviewed_at: string | null;
  terms_reviewed_by: string | null;
  active: boolean;
  created_at: string;
};

type IngestionRun = {
  id: string;
  source_id: string;
  status: string;
  adapter_name: string;
  requested_by: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  pages_fetched: number;
  records_fetched: number;
  records_created: number;
  records_updated: number;
  records_unchanged: number;
  records_failed: number;
  error_summary: string | null;
};

type IngestionConfig = {
  provider: string;
  configured_in_api_environment: boolean;
  appname_configured: boolean;
  country_scope: string[];
  limits: {
    initial_lookback_days: number;
    max_pages: number;
    page_size: number;
    overlap_hours: number;
  };
  note: string;
};

type OperationsSummary = {
  generated_at: string;
  provider_configured_in_api_environment: boolean;
  source_counts: {
    total: number;
    active: number;
    terms_review_required: number;
    provider_configuration_missing: number;
    never_ingested: number;
  };
  active_runs: number;
  runs_created_last_24h: { total: number; by_status: Record<string, number> };
  sources: Array<{
    id: string;
    name: string;
    source_type: string;
    active: boolean;
    license_status: string;
    terms_reviewed: boolean;
    operational_state: string;
    latest_run_status: string | null;
    latest_run_created_at: string | null;
    latest_run_finished_at: string | null;
    latest_checkpoint_updated_at: string | null;
    latest_watermark: string | null;
    hours_since_checkpoint: number | null;
  }>;
  note: string;
};

type Props = { accessToken: string };

const eligibleLicenseStatuses = new Set(["approved", "public_domain", "open_license", "licensed"]);

function prettyDate(value: string | null): string {
  if (!value) return "Not recorded";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Invalid date" : date.toLocaleString();
}

export default function AdminSourcesPanel({ accessToken }: Props) {
  const [sources, setSources] = useState<Source[]>([]);
  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [configuration, setConfiguration] = useState<IngestionConfig | null>(null);
  const [operations, setOperations] = useState<OperationsSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [attestations, setAttestations] = useState<Record<string, boolean>>({});
  const [termsRationales, setTermsRationales] = useState<Record<string, string>>({});
  const [sourceEdits, setSourceEdits] = useState<Record<string, { termsUrl: string; retentionPolicy: string }>>({});
  const [name, setName] = useState("ReliefWeb Reports — MENA");
  const [homepageUrl, setHomepageUrl] = useState("https://reliefweb.int/");
  const [termsUrl, setTermsUrl] = useState("");
  const [ownerName, setOwnerName] = useState("ReliefWeb / report contributors");
  const [retentionPolicy, setRetentionPolicy] = useState(
    "Store provider metadata and canonical URLs only; do not download report/article bodies. Retain metadata according to the reviewed source terms.",
  );

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const [sourcePage, runPage, providerConfig, ops] = await Promise.all([
        apiRequest<{ items: Source[] }>("/sources/admin?limit=200", accessToken),
        apiRequest<{ items: IngestionRun[] }>("/ingestion/runs?limit=50", accessToken),
        apiRequest<IngestionConfig>("/ingestion/configuration", accessToken),
        apiRequest<OperationsSummary>("/ingestion/operations", accessToken),
      ]);
      setSources(sourcePage.items);
      setSourceEdits(Object.fromEntries(sourcePage.items.map((source) => [source.id, { termsUrl: source.license_terms_url ?? "", retentionPolicy: source.retention_policy ?? "" }])));
      setRuns(runPage.items);
      setConfiguration(providerConfig);
      setOperations(ops);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to load source administration data.");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const sourceById = useMemo(
    () => new Map(sources.map((source) => [source.id, source])),
    [sources],
  );

  const registerSource = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setMessage(null);
    if (name.trim().length < 3) {
      setError("Enter a source name of at least three characters.");
      return;
    }
    if (!termsUrl.trim()) {
      setError("Enter the exact source terms URL. A source is registered inactive and cannot be activated without reviewed terms.");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: name.trim(),
        source_type: "reliefweb_reports",
        access_mode: "public_api",
        homepage_url: homepageUrl.trim() || undefined,
        license_terms_url: termsUrl.trim(),
        owner_name: ownerName.trim() || undefined,
        retention_policy: retentionPolicy.trim() || undefined,
        refresh_cadence: "manual",
      };
      const source = await apiRequest<Source>("/sources", accessToken, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setMessage(`Source registered as inactive (${source.id}). Review the actual terms before approving or activating it.`);
      setSources((current) => [source, ...current]);
      setName("");
      setTermsUrl("");
      setAttestations((current) => ({ ...current, [source.id]: false }));
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Source could not be registered.");
    } finally {
      setSaving(false);
    }
  }, [accessToken, homepageUrl, name, ownerName, refresh, retentionPolicy, termsUrl]);

  const patchSource = useCallback(async (
    source: Source,
    patch: Record<string, unknown>,
    successMessage: string,
  ) => {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await apiRequest<Source>(`/sources/${encodeURIComponent(source.id)}`, accessToken, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      setMessage(successMessage);
      setAttestations((current) => ({ ...current, [source.id]: false }));
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Source update was rejected.");
    } finally {
      setSaving(false);
    }
  }, [accessToken, refresh]);

  const queueRun = useCallback(async (source: Source) => {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const run = await apiRequest<IngestionRun>(
        `/ingestion/sources/${encodeURIComponent(source.id)}/runs`,
        accessToken,
        { method: "POST" },
      );
      setMessage(`Manual ingestion run ${run.id} queued. Check the run status; queueing is not proof that data was fetched.`);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Ingestion run was not queued.");
    } finally {
      setSaving(false);
    }
  }, [accessToken, refresh]);

  return (
    <section className="workspace-card admin-sources-card">
      <div className="section-heading">
        <h2>Administration · source registry</h2>
        <span>{loading ? "Refreshing…" : `${sources.length} source(s) registered`}</span>
      </div>
      {error && <p className="error-banner" role="alert">{error}</p>}
      {message && <p className="success-banner" role="status">{message}</p>}

      <section className="provider-config-panel">
        <div className="provider-config-head">
          <div>
            <h3>ReliefWeb connector configuration</h3>
            <p className="muted">This checks only the API-side environment. The worker must use the same app name and country scope.</p>
          </div>
          <span className={`status ${configuration?.configured_in_api_environment ? "status-configured" : ""}`}>
            {configuration?.configured_in_api_environment ? "Environment configured" : "Not configured"}
          </span>
        </div>
        <div className="provider-figures">
          <span>App name: <strong>{configuration?.appname_configured ? "Set (value hidden)" : "Missing"}</strong></span>
          <span>Country scope: <strong>{configuration?.country_scope.length ? configuration.country_scope.join(", ") : "Empty"}</strong></span>
          {configuration?.limits && (
            <span>Limits: <strong>{configuration.limits.page_size}/page · {configuration.limits.max_pages} pages/run · {configuration.limits.initial_lookback_days} day lookback · {configuration.limits.overlap_hours}h overlap</strong></span>
          )}
        </div>
        <p className="muted">{configuration?.note ?? "Checking provider configuration…"}</p>
      </section>

      {operations && (
        <section className="provider-config-panel ops-snapshot">
          <div className="provider-config-head">
            <div>
              <h3>Operational snapshot</h3>
              <p className="muted">Generated {prettyDate(operations.generated_at)} · timestamps and states only, not a truth or provider-connectivity claim.</p>
            </div>
            <button className="secondary-button" type="button" disabled={loading} onClick={() => void refresh()}>Refresh ops snapshot</button>
          </div>
          <div className="ops-metric-grid">
            <div><strong>{operations.source_counts.total}</strong><span>sources</span></div>
            <div><strong>{operations.source_counts.active}</strong><span>active</span></div>
            <div><strong>{operations.source_counts.terms_review_required}</strong><span>terms review needed</span></div>
            <div><strong>{operations.source_counts.never_ingested}</strong><span>never ingested</span></div>
            <div><strong>{operations.active_runs}</strong><span>queued/running/retrying</span></div>
            <div><strong>{operations.runs_created_last_24h.total}</strong><span>runs created, 24h</span></div>
          </div>
          <div className="ops-source-list">
            {operations.sources.map((item) => (
              <div className="ops-source-row" key={item.id}>
                <div className="document-row-head">
                  <span className={`review-pill ${item.operational_state.startsWith("completed") ? "review-approved" : ""}`}>{item.operational_state.replaceAll("_", " ")}</span>
                  <strong>{item.name}</strong>
                </div>
                <p className="muted">
                  Last run: {item.latest_run_status ?? "never"} · finished {prettyDate(item.latest_run_finished_at)}
                  {item.hours_since_checkpoint !== null ? ` · checkpoint age ${item.hours_since_checkpoint}h` : " · no checkpoint"}
                </p>
                {item.latest_watermark && <p className="document-hash">Provider watermark: {item.latest_watermark}</p>}
              </div>
            ))}
          </div>
          <p className="muted">{operations.note}</p>
        </section>
      )}

      <form className="admin-source-form" onSubmit={(event) => void registerSource(event)}>
        <h3>Register source (inactive by default)</h3>
        <div className="draft-two-col">
          <label>Display name
            <input required minLength={3} maxLength={240} value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>Provider homepage (HTTPS)
            <input type="url" value={homepageUrl} onChange={(event) => setHomepageUrl(event.target.value)} placeholder="https://…" />
          </label>
        </div>
        <label>Exact source terms / license URL (HTTPS)
          <input required type="url" value={termsUrl} onChange={(event) => setTermsUrl(event.target.value)} placeholder="Enter the actual terms reviewed by your organization" />
        </label>
        <label>Owner / contributor group
          <input maxLength={240} value={ownerName} onChange={(event) => setOwnerName(event.target.value)} />
        </label>
        <label>Retention and permitted-use note
          <textarea required minLength={20} maxLength={2000} rows={2} value={retentionPolicy} onChange={(event) => setRetentionPolicy(event.target.value)} />
        </label>
        <div className="document-actions">
          <button className="primary-button" type="submit" disabled={saving || !termsUrl.trim()}>{saving ? "Saving…" : "Register inactive source"}</button>
          <button className="secondary-button" type="button" disabled={saving || loading} onClick={() => void refresh()}>Refresh registry/runs</button>
        </div>
      </form>

      <div className="admin-source-list">
        <h3>Registered sources and controls</h3>
        {loading && sources.length === 0 ? <p className="muted">Loading source registry…</p> : sources.length === 0 ? (
          <div className="empty">No source has been registered yet. Register one above, review its terms, then activate it only after both API and worker provider configuration are ready.</div>
        ) : sources.map((source) => {
          const eligible = eligibleLicenseStatuses.has(source.license_status)
            && Boolean(source.terms_reviewed_at && source.terms_reviewed_by);
          const readyForActivation = Boolean(
            eligible && source.license_terms_url && source.terms_reviewed_at
            && source.terms_reviewed_by && source.retention_policy,
          );
          const editValues = sourceEdits[source.id] ?? { termsUrl: source.license_terms_url ?? "", retentionPolicy: source.retention_policy ?? "" };
          return (
            <article className="document-row" key={source.id}>
              <div className="document-row-head">
                <span className={`review-pill ${source.active ? "review-approved" : ""}`}>{source.active ? "active" : "inactive"}</span>
                <span className="review-pill">{source.license_status.replaceAll("_", " ")}</span>
                <span className="muted">{source.source_type}</span>
              </div>
              <h4>{source.name}</h4>
              <p className="muted">Created {prettyDate(source.created_at)} · terms review: {prettyDate(source.terms_reviewed_at)}</p>
              {source.license_terms_url && <p><a className="text-link" href={source.license_terms_url} target="_blank" rel="noopener noreferrer">Open source terms ↗</a></p>}
              <p className="document-hash">Source ID: {source.id}</p>
              <div className="source-edit-form">
                <label>Source terms URL (HTTPS)
                  <input
                    type="url"
                    required
                    value={editValues.termsUrl}
                    onChange={(event) => setSourceEdits((current) => ({ ...current, [source.id]: { ...editValues, termsUrl: event.target.value } }))}
                  />
                </label>
                <label>Retention / permitted-use note
                  <textarea
                    required
                    minLength={20}
                    maxLength={2000}
                    rows={2}
                    value={editValues.retentionPolicy}
                    onChange={(event) => setSourceEdits((current) => ({ ...current, [source.id]: { ...editValues, retentionPolicy: event.target.value } }))}
                  />
                </label>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={saving || !editValues.termsUrl.trim() || editValues.retentionPolicy.trim().length < 20}
                  onClick={() => void patchSource(
                    source,
                    { license_terms_url: editValues.termsUrl.trim(), retention_policy: editValues.retentionPolicy.trim() },
                    `Source terms/retention metadata saved for ${source.name}. If the terms URL changed, approval was invalidated and the source was deactivated.`,
                  )}
                >Save terms / retention</button>
              </div>
              {!source.active && !eligible && (
                <div className="source-attestation">
                  <label className="attestation-label">
                    <input
                      type="checkbox"
                      checked={Boolean(attestations[source.id])}
                      onChange={(event) => setAttestations((current) => ({ ...current, [source.id]: event.target.checked }))}
                    />
                    <span>I reviewed the linked terms for metadata access, attribution, reuse/redistribution and retention, and accept responsibility for this approval.</span>
                  </label>
                  <label className="attestation-rationale">Terms-review rationale (recorded in audit log)
                    <textarea
                      required
                      minLength={20}
                      maxLength={2000}
                      rows={2}
                      value={termsRationales[source.id] ?? ""}
                      onChange={(event) => setTermsRationales((current) => ({ ...current, [source.id]: event.target.value }))}
                      placeholder="Describe permitted use, attribution/reuse conditions, and the agreed retention boundary."
                    />
                  </label>
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={saving || !source.license_terms_url || !attestations[source.id] || (termsRationales[source.id] ?? "").trim().length < 20}
                    onClick={() => void patchSource(
                      source,
                      { license_status: "approved", terms_review_rationale: (termsRationales[source.id] ?? "").trim() },
                      `Terms approval recorded for ${source.name}. Source remains inactive.`,
                    )}
                  >Approve reviewed terms</button>
                </div>
              )}
              <div className="document-actions">
                {source.active ? (
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={saving}
                    onClick={() => {
                      if (window.confirm("Deactivate this source? Published events with no other qualifying evidence may be removed from the public feed.")) {
                        void patchSource(source, { active: false }, `${source.name} deactivated.`);
                      }
                    }}
                  >Deactivate source</button>
                ) : (
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={saving || !readyForActivation}
                    onClick={() => {
                      if (window.confirm("Activate this source for manual ingestion? The API and worker provider settings must match; each imported document will still require human review.")) {
                        void patchSource(source, { active: true }, `${source.name} activated; it is not yet a published data feed.`);
                      }
                    }}
                  >Activate source</button>
                )}
                {source.active && eligible && (
                  <button
                    className="primary-button"
                    type="button"
                    disabled={saving || !configuration?.configured_in_api_environment}
                    onClick={() => void queueRun(source)}
                  >Queue manual ingestion</button>
                )}
                {source.active && !configuration?.configured_in_api_environment && (
                  <span className="muted">Configure ReliefWeb app name/country scope in both API and worker before running.</span>
                )}
              </div>
            </article>
          );
        })}
      </div>

      <div className="admin-runs-panel">
        <div className="section-heading">
          <h3>Recent ingestion runs</h3>
          <span>{runs.length} run(s)</span>
        </div>
        {runs.length === 0 ? <div className="empty">No ingestion has been queued. Manual runs remain disabled until a source is approved/active and provider settings are configured.</div> : (
          <div className="run-list">
            {runs.slice(0, 30).map((run) => (
              <article key={run.id} className="run-row">
                <div className="document-row-head">
                  <span className={`review-pill ${run.status.startsWith("completed") ? "review-approved" : ""}`}>{run.status.replaceAll("_", " ")}</span>
                  <strong>{sourceById.get(run.source_id)?.name ?? run.source_id}</strong>
                </div>
                <p className="muted">Created {prettyDate(run.created_at)} · started {prettyDate(run.started_at)} · finished {prettyDate(run.finished_at)}</p>
                <p className="run-metrics">Pages {run.pages_fetched} · fetched {run.records_fetched} · new {run.records_created} · updated {run.records_updated} · unchanged {run.records_unchanged} · failed {run.records_failed}</p>
                {run.error_summary && <p className="muted">{run.error_summary}</p>}
                <p className="document-hash">Run ID: {run.id}</p>
              </article>
            ))}
          </div>
        )}
      </div>
      <p className="muted admin-safety-note">The admin console never treats source registration or ingestion as event verification. Imported source documents enter the review queue; only an independently reviewed event with eligible linked evidence can be published.</p>
    </section>
  );
}
