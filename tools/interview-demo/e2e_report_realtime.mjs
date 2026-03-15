const API_BASE = process.env.API_BASE || "http://localhost:8000";
const WS_BASE = process.env.WS_BASE || "ws://localhost:8006";
const TENANT_ID = process.env.TENANT_ID || "tenant-a";
const STUDY_ID = process.env.STUDY_ID || "study-a";
const USERNAME = process.env.USERNAME || "researcher";
const PASSWORD = process.env.PASSWORD || "researcher123";

async function login() {
  const response = await fetch(`${API_BASE}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD })
  });
  if (!response.ok) throw new Error(`login failed: ${response.status}`);
  const payload = await response.json();
  return payload.access_token;
}

async function fetchReport(token) {
  const response = await fetch(`${API_BASE}/reports/studies/${STUDY_ID}?page=1&page_size=20`, {
    headers: {
      Authorization: `Bearer ${token}`,
      "x-tenant-id": TENANT_ID
    }
  });
  if (!response.ok) throw new Error(`report failed: ${response.status}`);
  return response.json();
}

async function wsSnapshot(token) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`${WS_BASE}/ws/studies/${STUDY_ID}?tenant_id=${TENANT_ID}&token=${token}`);
    const timeout = setTimeout(() => {
      ws.close();
      reject(new Error("ws timeout"));
    }, 8000);

    ws.onmessage = (event) => {
      clearTimeout(timeout);
      ws.close();
      resolve(JSON.parse(event.data));
    };
    ws.onerror = () => {
      clearTimeout(timeout);
      reject(new Error("ws error"));
    };
  });
}

async function main() {
  const token = await login();
  const report = await fetchReport(token);
  const snap = await wsSnapshot(token);

  if (!report || !report.study_id) throw new Error("invalid report payload");
  if (!snap || !snap.widgets) throw new Error("invalid websocket payload");
  console.log(
    JSON.stringify(
      {
        ok: true,
        reportStudyId: report.study_id,
        widgets: Object.keys(snap.widgets)
      },
      null,
      2
    )
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
