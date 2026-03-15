import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import {
  buildReportUrl,
  filterVisibleTemplates,
  getAuthHeaders,
  inferRole,
  paginateTemplates,
  type DashboardTemplate
} from "./lib/dashboard";

type TokenResponse = { access_token: string; token_type: string };
type RealtimePayload = {
  tenant_id: string;
  study_id: string;
  role: string;
  widgets: Record<string, { total?: number; critical?: number; events?: number }>;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const REALTIME_BASE_URL = import.meta.env.VITE_REALTIME_BASE_URL || "ws://localhost:8006";
const LazyPlot = lazy(() => import("react-plotly.js"));

export function App() {
  const [username, setUsername] = useState("researcher");
  const [password, setPassword] = useState("researcher123");
  const [tenantId, setTenantId] = useState("tenant-a");
  const [studyId, setStudyId] = useState("study-a");
  const [token, setToken] = useState("");
  const [role, setRole] = useState("researcher");
  const [templates, setTemplates] = useState<DashboardTemplate[]>([]);
  const [report, setReport] = useState<any>(null);
  const [latencyMs, setLatencyMs] = useState<number>(0);
  const [realtime, setRealtime] = useState<RealtimePayload | null>(null);
  const [page, setPage] = useState(1);
  const [participantFilter, setParticipantFilter] = useState("");
  const [templatePage, setTemplatePage] = useState(1);

  const authHeaders = useMemo(
    () => getAuthHeaders(token, tenantId),
    [token, tenantId]
  );

  const login = async () => {
    const response = await fetch(`${API_BASE_URL}/auth/token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    if (!response.ok) throw new Error("Login failed");
    const payload = (await response.json()) as TokenResponse;
    setToken(payload.access_token);
    setRole(inferRole(username));
  };

  const loadTemplates = async () => {
    const response = await fetch(`${API_BASE_URL}/reports/templates?role=${role}`, { headers: authHeaders });
    if (!response.ok) throw new Error("Failed to load templates");
    const payload = await response.json();
    setTemplates(payload.dashboards || []);
  };

  const loadReport = async () => {
    const started = performance.now();
    const url = buildReportUrl(API_BASE_URL, studyId, page, 25, participantFilter);
    const response = await fetch(url, { headers: authHeaders });
    if (!response.ok) throw new Error("Failed to load report");
    setReport(await response.json());
    setLatencyMs(performance.now() - started);
  };

  useEffect(() => {
    if (!token) return;
    void loadTemplates();
    void loadReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, role, page, participantFilter, studyId]);

  useEffect(() => {
    if (!token) return;
    const ws = new WebSocket(`${REALTIME_BASE_URL}/ws/studies/${studyId}?tenant_id=${tenantId}&token=${token}`);
    ws.onmessage = (event) => {
      setRealtime(JSON.parse(event.data) as RealtimePayload);
    };
    return () => ws.close();
  }, [token, tenantId, studyId]);

  const visibleTemplates = filterVisibleTemplates(templates, role);
  const templatePageSize = 24;
  const pagedTemplates = paginateTemplates(visibleTemplates, templatePage, templatePageSize);

  return (
    <div className="container">
      <header>
        <h1>UbiWell Metadata-Driven Dashboards</h1>
        <p>Role-based + realtime + paginated report views for high daily user traffic.</p>
      </header>

      <section className="panel">
        <h2>Auth</h2>
        <div className="row">
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username" />
          <input value={password} onChange={(e) => setPassword(e.target.value)} placeholder="password" type="password" />
          <input value={tenantId} onChange={(e) => setTenantId(e.target.value)} placeholder="tenant id" />
          <input value={studyId} onChange={(e) => setStudyId(e.target.value)} placeholder="study id" />
          <button onClick={() => void login()}>Login</button>
        </div>
        <p>Current role: {role}</p>
      </section>

      <section className="grid">
        <div className="panel">
          <h2>Realtime Widgets</h2>
          <pre>{JSON.stringify(realtime, null, 2)}</pre>
        </div>

        <div className="panel">
          <h2>Report API</h2>
          <p>API latency: {latencyMs.toFixed(1)} ms</p>
          <div className="row">
            <input
              value={participantFilter}
              onChange={(e) => setParticipantFilter(e.target.value)}
              placeholder="participant filter"
            />
            <button onClick={() => setPage((p) => Math.max(1, p - 1))}>Prev</button>
            <span>Page {page}</span>
            <button onClick={() => setPage((p) => p + 1)}>Next</button>
          </div>
          <pre>{JSON.stringify(report, null, 2)}</pre>
        </div>
      </section>

      <section className="panel">
        <h2>Dashboard Catalog ({visibleTemplates.length})</h2>
        <p>Templates are metadata-driven (scales to 100+ dashboards without manual pages).</p>
        <div className="row">
          <button onClick={() => setTemplatePage((p) => Math.max(1, p - 1))}>Prev Catalog Page</button>
          <span>Catalog Page {templatePage}</span>
          <button onClick={() => setTemplatePage((p) => p + 1)}>Next Catalog Page</button>
        </div>
        <div className="cards">
          {pagedTemplates.map((template) => (
            <article key={template.id} className="card">
              <h3>{template.title}</h3>
              <p>{template.id}</p>
              <small>{template.chartType}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>Telemetry Plot (Plotly)</h2>
        <Suspense fallback={<p>Loading chart bundle...</p>}>
          <LazyPlot
            data={[
              {
                x: (report?.telemetry || []).map((x: any) => x.event_type),
                y: (report?.telemetry || []).map((x: any) => x.count),
                type: "bar"
              }
            ]}
            layout={{ width: 900, height: 320, title: "Events by Type" }}
          />
        </Suspense>
      </section>
    </div>
  );
}
