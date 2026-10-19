"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { User } from "oidc-client-ts";
import {
  apiRequest,
  createOidcUserManager,
  isOidcConfigured,
  loadRuntimeConfig,
  type ApiPrincipal,
  type RuntimePublicConfig,
} from "../../lib/oidc";
import type { UserManager } from "oidc-client-ts";

type DocumentStatus = "pending_review" | "approved" | "provisional" | "disputed" | "rejected" | "needs_more_evidence";
type EventType =
  | "armed_clash_reported" | "airstrike_reported" | "civilian_casualties" | "mass_casualty"
  | "displacement" | "infrastructure_damage" | "humanitarian_access" | "blockade_violation"
  | "explosive_hazard" | "detention" | "protection_incident" | "perpetrator_attribution" | "other";

type SourceDocument = {
  id: string;
  source_id: string;
  source_name: string | null;
  title: string;
  canonical_url: string;
  published_at: string | null;
  retrieved_at: string;
  content_hash: string;
  license_note: string | null;
  metadata: Record<string, unknown>;
  review_status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_rationale: string | null;
  external_ids: string[];
};

type ReviewTaskStatus = "pending" | "in_review" | "needs_more_evidence" | "completed" | "cancelled";
type ReviewDecision = "verify" | "accept_provisional" | "dispute" | "reject" | "request_more_evidence";
type ReviewTask = {
  id: string;
  subject_type: "event" | "source_document";
  subject_id: string;
  status: ReviewTaskStatus;
  priority: string;
  created_at: string;
  subject_title: string | null;
  canonical_url: string | null;
  source_name: string | null;
  event_type: string | null;
  event_status: string | null;
  verification_status: string | null;
  country_code: string | null;
  document_review_status: string | null;
  event_summary: string | null;
};

type DraftForm = {
  event_type: EventType;
  summary: string;
  event_start: string;
  event_end: string;
  country_code: string;
  latitude: string;
  longitude: string;
  spatial_uncertainty_m: string;
  rationale: string;
};

const initialDraft: DraftForm = {
  event_type: "infrastructure_damage",
  summary: "",
  event_start: "",
  event_end: "",
  country_code: "",
  latitude: "",
  longitude: "",
  spatial_uncertainty_m: "",
  rationale: "",
};

const eventTypes: { value: EventType; label: string }[] = [
  { value: "armed_clash_reported", label: "Armed clash (reported)" },
  { value: "airstrike_reported", label: "Airstrike (reported)" },
  { value: "civilian_casualties", label: "Civilian casualties" },
  { value: "mass_casualty", label: "Mass casualty" },
  { value: "displacement", label: "Displacement" },
  { value: "infrastructure_damage", label: "Infrastructure damage" },
  { value: "humanitarian_access", label: "Humanitarian access" },
  { value: "blockade_violation", label: "Blockade violation" },
  { value: "explosive_hazard", label: "Explosive hazard" },
  { value: "detention", label: "Detention" },
  { value: "protection_incident", label: "Protection incident" },
  { value: "perpetrator_attribution", label: "Perpetrator attribution (high-impact review)" },
  { value: "other", label: "Other / uncategorized" },
];

function safeDate(value: string | null): string {
  if (!value) return "Not provided";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unparseable source date" : date.toLocaleString();
}

function metadataList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0);
}

export default function AnalystWorkspace() {
  const [config, setConfig] = useState<RuntimePublicConfig | null>(null);
  const [manager, setManager] = useState<UserManager | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [principal, setPrincipal] = useState<ApiPrincipal | null>(null);
  const [booting, setBooting] = useState(true);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [documentStatus, setDocumentStatus] = useState<DocumentStatus>("approved");
  const [reviewTasks, setReviewTasks] = useState<ReviewTask[]>([]);
  const [reviewTaskStatus, setReviewTaskStatus] = useState<ReviewTaskStatus>("pending");
  const [loadingReviewTasks, setLoadingReviewTasks] = useState(false);
  const [reviewRationales, setReviewRationales] = useState<Record<string, string>>({});
  const [reviewingTaskId, setReviewingTaskId] = useState<string | null>(null);
  const [publishingEventId, setPublishingEventId] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [callbackUrl, setCallbackUrl] = useState("/auth/callback");
  const [selectedDocument, setSelectedDocument] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftForm>(initialDraft);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const accessToken = user?.access_token ?? "";

  const roles = principal?.roles ?? [];
  const canDraft = roles.some((role) => ["analyst", "reviewer", "admin"].includes(role));
  const canReview = roles.some((role) => ["reviewer", "admin"].includes(role));
  const canPublish = roles.some((role) => ["publisher", "admin"].includes(role));
  const canAccessReviewQueue = roles.some((role) => ["reviewer", "publisher", "admin"].includes(role));

  useEffect(() => {
    setCallbackUrl(`${window.location.origin}/auth/callback`);
  }, []);

  useEffect(() => {
    let active = true;
    async function initialize() {
      try {
        const runtime = await loadRuntimeConfig();
        if (!active) return;
        setConfig(runtime);
        if (!isOidcConfigured(runtime)) {
          setBooting(false);
          return;
        }
        const oidcManager = createOidcUserManager(runtime);
        const storedUser = await oidcManager.getUser();
        if (!active) return;
        setManager(oidcManager);
        if (storedUser && !storedUser.expired && storedUser.access_token) {
          setUser(storedUser);
        } else {
          if (storedUser) await oidcManager.removeUser();
          setUser(null);
        }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Workspace initialization failed.");
      } finally {
        if (active) setBooting(false);
      }
    }
    void initialize();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!manager || !accessToken) {
      setPrincipal(null);
      setDocuments([]);
      setReviewTasks([]);
      return;
    }
    let active = true;
    async function loadWorkspace() {
      setLoadingDocs(true);
      setLoadingReviewTasks(true);
      setError(null);
      try {
        const who = await apiRequest<ApiPrincipal>("/auth/me", accessToken);
        if (!active) return;
        setPrincipal(who);
        if (!who.roles.some((role) => ["analyst", "reviewer", "publisher", "admin"].includes(role))) {
          setDocuments([]);
          setReviewTasks([]);
          setError("Your access token is valid but has no role permitted to inspect source documents.");
          return;
        }
        const page = await apiRequest<{ items: SourceDocument[]; note?: string }>(
          `/ingestion/documents?review_status=${encodeURIComponent(documentStatus)}&limit=100`,
          accessToken,
        );
        if (active) setDocuments(page.items);

        const roleCanOpenQueue = who.roles.some((role) => ["reviewer", "publisher", "admin"].includes(role));
        if (roleCanOpenQueue) {
          const tasks = await apiRequest<{ items: ReviewTask[] }>(
            `/reviews/tasks?status=${encodeURIComponent(reviewTaskStatus)}`,
            accessToken,
          );
          if (active) setReviewTasks(tasks.items);
        } else if (active) {
          setReviewTasks([]);
        }
      } catch (cause) {
        if (!active) return;
        setDocuments([]);
        setReviewTasks([]);
        setPrincipal(null);
        setError(cause instanceof Error ? cause.message : "Unable to load authenticated workspace data.");
        if (cause instanceof Error && cause.message.includes("expired")) {
          await manager?.removeUser();
          setUser(null);
        }
      } finally {
        if (active) {
          setLoadingDocs(false);
          setLoadingReviewTasks(false);
        }
      }
    }
    void loadWorkspace();
    return () => { active = false; };
  }, [manager, accessToken, documentStatus, reviewTaskStatus, refreshTick]);

  const sourceCounts = useMemo(() => ({
    loaded: documents.length,
    approved: documents.filter((document) => document.review_status === "approved").length,
  }), [documents]);

  const signIn = useCallback(async () => {
    setError(null);
    setMessage(null);
    if (!manager) {
      setError("OIDC is not configured for this deployment.");
      return;
    }
    try {
      await manager.signinRedirect();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to start sign-in.");
    }
  }, [manager]);

  const signOut = useCallback(async () => {
    setError(null);
    if (!manager) {
      setUser(null);
      setPrincipal(null);
      return;
    }
    try {
      await manager.signoutRedirect();
    } catch {
      await manager.removeUser();
      setUser(null);
      setPrincipal(null);
      setDocuments([]);
      setMessage("Local session cleared. The identity provider may still have an active browser session.");
    }
  }, [manager]);

  const submitDraft = useCallback(async (documentId: string) => {
    if (!canDraft || !accessToken) {
      setError("Your assigned role does not allow event-draft creation.");
      return;
    }
    const hasLatitude = draft.latitude.trim() !== "";
    const hasLongitude = draft.longitude.trim() !== "";
    if (hasLatitude !== hasLongitude) {
      setError("Provide both latitude and longitude, or leave both blank.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const payload: Record<string, unknown> = {
        event_type: draft.event_type,
        summary: draft.summary.trim(),
        rationale: draft.rationale.trim(),
      };
      if (draft.event_start) payload.event_start = new Date(draft.event_start).toISOString();
      if (draft.event_end) payload.event_end = new Date(draft.event_end).toISOString();
      if (draft.country_code.trim()) payload.country_code = draft.country_code.trim().toUpperCase();
      if (draft.latitude.trim() !== "" && draft.longitude.trim() !== "") {
        payload.latitude = Number(draft.latitude);
        payload.longitude = Number(draft.longitude);
        if (draft.spatial_uncertainty_m.trim()) {
          payload.spatial_uncertainty_m = Number(draft.spatial_uncertainty_m);
        }
      }
      const result = await apiRequest<{
        event_id: string; event_status: string; verification_status: string;
        published: boolean; message: string;
      }>(`/events/drafts/from-document/${encodeURIComponent(documentId)}`, accessToken, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setMessage(`Draft ${result.event_id} created as ${result.event_status}; it is not published.`);
      setSelectedDocument(null);
      setDraft(initialDraft);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Draft could not be created.");
    } finally {
      setSubmitting(false);
    }
  }, [accessToken, canDraft, draft]);

  const submitReviewDecision = useCallback(async (task: ReviewTask, decision: ReviewDecision) => {
    if (!canReview || !accessToken) {
      setError("Your role does not allow review decisions.");
      return;
    }
    const rationale = (reviewRationales[task.id] ?? "").trim();
    if (rationale.length < 10) {
      setError("Enter a review rationale of at least 10 characters before recording a decision.");
      return;
    }
    setReviewingTaskId(task.id);
    setError(null);
    setMessage(null);
    try {
      const result = await apiRequest<{
        task_status: string;
        event_status: string | null;
        verification_status: string | null;
        source_document_review_status: string | null;
        published: boolean;
      }>(`/reviews/tasks/${encodeURIComponent(task.id)}/decisions`, accessToken, {
        method: "POST",
        body: JSON.stringify({ decision, rationale }),
      });
      const state = result.source_document_review_status
        ? `source document is now ${result.source_document_review_status}`
        : `event is now ${result.event_status ?? "pending review"} / ${result.verification_status ?? "unverified"}`;
      setMessage(`Review saved: ${state}. Publication was not triggered.`);
      setReviewRationales((current) => ({ ...current, [task.id]: "" }));
      setRefreshTick((value) => value + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Review decision could not be saved.");
    } finally {
      setReviewingTaskId(null);
    }
  }, [accessToken, canReview, reviewRationales]);

  const publishEvent = useCallback(async (task: ReviewTask) => {
    if (!canPublish || !accessToken || task.subject_type !== "event") {
      setError("Your role does not allow publication.");
      return;
    }
    if (!["verified", "provisional"].includes(task.verification_status ?? "")) {
      setError("This event has not received an eligible review status.");
      return;
    }
    setPublishingEventId(task.subject_id);
    setError(null);
    setMessage(null);
    try {
      const result = await apiRequest<{ status: string; verification_status: string }>(
        `/events/${encodeURIComponent(task.subject_id)}/publish`,
        accessToken,
        { method: "POST" },
      );
      setMessage(`Publication action accepted by API: event ${task.subject_id} is ${result.status} / ${result.verification_status}. Check evidence and audit record before relying on it.`);
      setReviewTaskStatus("completed");
      setRefreshTick((value) => value + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Publication failed the API gates.");
    } finally {
      setPublishingEventId(null);
    }
  }, [accessToken, canPublish]);

  if (booting) {
    return <main className="shell workspace-shell"><section className="workspace-card"><p>Loading deployment configuration…</p></section></main>;
  }

  if (!config || !isOidcConfigured(config)) {
    return (
      <main className="shell workspace-shell">
        <header className="workspace-header">
          <div><div className="eyebrow">MCHO ANALYST CONSOLE</div><h1>Analyst workspace</h1></div>
          <Link className="text-link" href="/">← Public observatory</Link>
        </header>
        <section className="workspace-card">
          <span className="status">Authentication not configured</span>
          <h2>Connect an identity provider first</h2>
          <p>This workspace intentionally has no token-paste sign-in and does not expose privileged actions before OIDC is configured.</p>
          <p className="muted">Set <code>MCHO_OIDC_AUTHORITY</code> and <code>MCHO_OIDC_CLIENT_ID</code> on the web service, then align the API’s <code>OIDC_ISSUER</code>, <code>OIDC_AUDIENCE</code>, and <code>OIDC_JWKS_URL</code>. Configure the exact callback URL shown below in your identity provider.</p>
          <code className="callback-url">{callbackUrl}</code>
          <p><a className="text-link" href="https://github.com/codex0786/mcho-mvp/blob/main/docs/security-oidc.md" target="_blank" rel="noopener noreferrer">OIDC setup guide ↗</a></p>
        </section>
        {error && <p className="error-banner" role="alert">{error}</p>}
      </main>
    );
  }

  return (
    <main className="shell workspace-shell">
      <header className="workspace-header">
        <div>
          <div className="eyebrow">MCHO ANALYST CONSOLE</div>
          <h1>Source review &amp; event drafting</h1>
          <p className="muted">Human-reviewed reports become draft claims—not automatic facts.</p>
        </div>
        <div className="header-actions">
          <Link className="text-link" href="/">← Public observatory</Link>
          {user && <button className="secondary-button" type="button" onClick={() => void signOut()}>Sign out</button>}
        </div>
      </header>

      {error && <p className="error-banner" role="alert">{error}</p>}
      {message && <p className="success-banner" role="status">{message}</p>}

      {!user || !accessToken ? (
        <section className="workspace-card sign-in-card">
          <span className="status">Protected workspace</span>
          <h2>Sign in to continue</h2>
          <p>Use your organization’s identity provider. Access is enforced again by the API for every privileged operation.</p>
          <button className="primary-button" type="button" onClick={() => void signIn()}>Sign in securely</button>
          <p className="muted">Authorization Code + PKCE · No client secret in the browser · Access token held in session scope</p>
        </section>
      ) : (
        <>
          <section className="identity-strip">
            <div>
              <span className="muted">Signed in</span>
              <strong>{principal?.subject ?? user.profile.sub ?? "Authenticated user"}</strong>
              <small>{principal?.issuer ?? "Validating roles with API…"}</small>
            </div>
            <div className="role-chips">
              {roles.length ? roles.map((role) => <span key={role} className="role-chip">{role}</span>) : <span className="role-chip">roles pending</span>}
            </div>
          </section>

          <section className="workspace-toolbar">
            <label>Document review state
              <select value={documentStatus} onChange={(event) => setDocumentStatus(event.target.value as DocumentStatus)}>
                <option value="pending_review">Pending source review</option>
                <option value="approved">Approved for drafting</option>
                <option value="provisional">Provisional</option>
                <option value="disputed">Disputed</option>
                <option value="needs_more_evidence">Needs more evidence</option>
                <option value="rejected">Rejected</option>
              </select>
            </label>
            <div className="workspace-metrics"><strong>{sourceCounts.loaded}</strong><span>documents shown</span><strong>{sourceCounts.approved}</strong><span>approved in current view</span></div>
            <button className="secondary-button" type="button" onClick={() => setRefreshTick((value) => value + 1)}>Refresh documents</button>
          </section>

          <div className="workspace-grid">
            <section className="workspace-card">
              <div className="section-heading">
                <h2>Source documents</h2>
                <span>{loadingDocs ? "Loading…" : "Metadata and canonical links only"}</span>
              </div>
              {loadingDocs ? <p className="muted">Loading document queue…</p> : documents.length === 0 ? (
                <div className="empty">No documents match this state, or the configured source has not ingested anything. An empty result is not evidence that no event occurred.</div>
              ) : (
                <div className="document-list">
                  {documents.map((document) => {
                    const countries = metadataList(document.metadata?.countries);
                    return (
                      <article className="document-row" key={document.id}>
                        <div className="document-row-head">
                          <span className={`review-pill review-${document.review_status}`}>{document.review_status.replaceAll("_", " ")}</span>
                          <span className="muted">{document.source_name ?? "Unknown source"}</span>
                        </div>
                        <h3>{document.title}</h3>
                        <p className="muted">Published: {safeDate(document.published_at)} · Retrieved: {safeDate(document.retrieved_at)}</p>
                        {countries.length > 0 && <p className="document-countries">Country tags: {countries.join(", ")}</p>}
                        <p className="document-hash">SHA-256: {document.content_hash.slice(0, 16)}…</p>
                        <div className="document-actions">
                          <a className="text-link" href={document.canonical_url} target="_blank" rel="noopener noreferrer">Open source report ↗</a>
                          {document.review_status === "approved" && canDraft && (
                            <button className="secondary-button" type="button" onClick={() => {
                              setSelectedDocument(document.id);
                              setDraft(initialDraft);
                              setError(null);
                              setMessage(null);
                            }}>Create event draft</button>
                          )}
                        </div>
                        {selectedDocument === document.id && canDraft && (
                          <form className="draft-form" onSubmit={(event) => { event.preventDefault(); void submitDraft(document.id); }}>
                            <h4>Human-authored draft</h4>
                            <p className="muted">This will create an unverified, unpublished candidate and a review task.</p>
                            <label>Event type
                              <select value={draft.event_type} onChange={(event) => setDraft((old) => ({ ...old, event_type: event.target.value as EventType }))}>
                                {eventTypes.map((type) => <option value={type.value} key={type.value}>{type.label}</option>)}
                              </select>
                            </label>
                            <label>Summary <span className="muted">· state only what the report supports</span>
                              <textarea required minLength={15} maxLength={5000} rows={3} value={draft.summary} onChange={(event) => setDraft((old) => ({ ...old, summary: event.target.value }))} placeholder="A reviewed report states…; attribution remains unknown unless independently supported." />
                            </label>
                            <div className="draft-two-col">
                              <label>Event start (local time)
                                <input type="datetime-local" value={draft.event_start} onChange={(event) => setDraft((old) => ({ ...old, event_start: event.target.value }))} />
                              </label>
                              <label>Event end (local time)
                                <input type="datetime-local" value={draft.event_end} onChange={(event) => setDraft((old) => ({ ...old, event_end: event.target.value }))} />
                              </label>
                            </div>
                            <label>Country code (ISO alpha-2)
                              <input maxLength={2} pattern="[A-Za-z]{2}" value={draft.country_code} onChange={(event) => setDraft((old) => ({ ...old, country_code: event.target.value.toUpperCase() }))} placeholder="LB" />
                            </label>
                            <div className="draft-two-col">
                              <label>Latitude (optional)
                                <input type="number" min={-90} max={90} step="any" value={draft.latitude} onChange={(event) => setDraft((old) => ({ ...old, latitude: event.target.value }))} />
                              </label>
                              <label>Longitude (optional)
                                <input type="number" min={-180} max={180} step="any" value={draft.longitude} onChange={(event) => setDraft((old) => ({ ...old, longitude: event.target.value }))} />
                              </label>
                            </div>
                            <label>Spatial uncertainty, metres (required with a point)
                              <input type="number" min={1} max={100000} step={1} value={draft.spatial_uncertainty_m} onChange={(event) => setDraft((old) => ({ ...old, spatial_uncertainty_m: event.target.value }))} />
                            </label>
                            <label>Draft rationale
                              <textarea required minLength={15} maxLength={5000} rows={2} value={draft.rationale} onChange={(event) => setDraft((old) => ({ ...old, rationale: event.target.value }))} placeholder="Explain interpretation, time/location uncertainty and any material omissions." />
                            </label>
                            <div className="document-actions">
                              <button className="primary-button" type="submit" disabled={submitting}>{submitting ? "Creating draft…" : "Create unpublished draft"}</button>
                              <button className="secondary-button" type="button" disabled={submitting} onClick={() => setSelectedDocument(null)}>Cancel</button>
                            </div>
                          </form>
                        )}
                      </article>
                    );
                  })}
                </div>
              )}
            </section>

            <aside className="workspace-card process-card">
              <h2>Evidence &amp; publication rules</h2>
              <ol>
                <li>Provider metadata is not itself a verified event.</li>
                <li>An analyst must open and assess the canonical source link before drafting.</li>
                <li>The draft includes a reported claim, source evidence link, revision and review task.</li>
                <li>Review decisions and publication use separate API calls and permissions.</li>
                <li>High-impact claim types require verified status before publication.</li>
              </ol>
              <div className="section-divider" />
              <h3>Current state</h3>
              <p className="muted">{canDraft ? "Your role allows draft creation from individually approved source documents." : "Your role can inspect eligible source metadata, but cannot create event drafts."}</p>
              <p className="muted">No source article body is copied into this workspace. If a source is stale, unavailable, disputed or outside permitted terms, do not use it as publication evidence.</p>
            </aside>
          </div>

          {(canReview || canPublish) && (
            <section className="workspace-card review-queue-card">
              <div className="section-heading">
                <h2>Review queue &amp; publication</h2>
                <span>{loadingReviewTasks ? "Loading tasks…" : `${reviewTasks.length} task(s) in this view`}</span>
              </div>
              <div className="workspace-toolbar">
                <label>Task state
                  <select value={reviewTaskStatus} onChange={(event) => setReviewTaskStatus(event.target.value as ReviewTaskStatus)}>
                    <option value="pending">Pending</option>
                    <option value="in_review">In review</option>
                    <option value="needs_more_evidence">Needs more evidence</option>
                    <option value="completed">Completed / ready for publication check</option>
                    <option value="cancelled">Cancelled</option>
                  </select>
                </label>
                <button className="secondary-button" type="button" disabled={loadingReviewTasks} onClick={() => setRefreshTick((value) => value + 1)}>Refresh queue</button>
              </div>
              {loadingReviewTasks ? (
                <p className="muted">Loading review tasks…</p>
              ) : reviewTasks.length === 0 ? (
                <div className="empty">No tasks in this state. An empty queue does not imply there are no reports or events.</div>
              ) : (
                <div className="document-list">
                  {reviewTasks.map((task) => (
                    <article className="document-row" key={task.id}>
                      <div className="document-row-head">
                        <span className={`review-pill review-${task.status}`}>{task.status.replaceAll("_", " ")}</span>
                        <span className="review-pill">{task.subject_type.replaceAll("_", " ")}</span>
                        <span className="muted">Priority: {task.priority}</span>
                      </div>
                      <h3>{task.subject_title ?? `Missing ${task.subject_type} record`}</h3>
                      <p className="muted">
                        Created: {safeDate(task.created_at)} · {task.event_type ? `Type: ${task.event_type} · ` : ""}
                        {task.country_code ? `Country: ${task.country_code} · ` : ""}
                        {task.event_status ? `Event: ${task.event_status} · ` : ""}
                        {task.verification_status ? `Verification: ${task.verification_status}` : ""}
                      </p>
                      {task.source_name && <p className="document-countries">Source: {task.source_name}</p>}
                      {task.canonical_url && (
                        <p><a className="text-link" href={task.canonical_url} target="_blank" rel="noopener noreferrer">Open canonical source ↗</a></p>
                      )}
                      {canReview && ["pending", "in_review", "needs_more_evidence"].includes(task.status) && (
                        <div className="draft-form">
                          <label>Reason for review decision
                            <textarea
                              minLength={10}
                              maxLength={5000}
                              rows={2}
                              required
                              value={reviewRationales[task.id] ?? ""}
                              onChange={(event) => setReviewRationales((current) => ({ ...current, [task.id]: event.target.value }))}
                              placeholder="State what the source supports, what remains uncertain, and why this disposition is appropriate."
                            />
                          </label>
                          <div className="document-actions">
                            {([
                              ["verify", task.subject_type === "source_document" ? "Approve source document" : "Verify event claim"],
                              ["accept_provisional", "Accept provisionally"],
                              ["request_more_evidence", "Request more evidence"],
                              ["dispute", "Dispute"],
                              ["reject", "Reject"],
                            ] as const).map(([decision, label]) => (
                              <button
                                key={decision}
                                className={decision === "verify" ? "primary-button" : "secondary-button"}
                                type="button"
                                disabled={reviewingTaskId === task.id}
                                onClick={() => void submitReviewDecision(task, decision)}
                              >
                                {reviewingTaskId === task.id ? "Saving…" : label}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                      {canPublish && task.subject_type === "event" && task.status === "completed"
                        && ["verified", "provisional"].includes(task.verification_status ?? "")
                        && task.event_status !== "withdrawn"
                        && task.event_status !== "published" && (
                          <div className="document-actions publish-actions">
                            <button
                              className="primary-button"
                              type="button"
                              disabled={publishingEventId === task.subject_id}
                              onClick={() => void publishEvent(task)}
                            >
                              {publishingEventId === task.subject_id ? "Checking gates…" : "Publish separately"}
                            </button>
                            <span className="muted">The API re-checks evidence eligibility and verification policy before publishing.</span>
                          </div>
                        )}
                    </article>
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}
      <footer>Analyst tools are gated by API-verified OIDC roles. Data shown here is source metadata and analyst-authored drafts; publication remains a separate audited action.</footer>
    </main>
  );
}
