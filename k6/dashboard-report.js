import http from "k6/http";
import ws from "k6/ws";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    report_and_templates_api: {
      executor: "constant-arrival-rate",
      rate: 8,
      timeUnit: "1s",
      duration: "3m",
      preAllocatedVUs: 20,
      maxVUs: 120
    },
    websocket_fanout: {
      executor: "constant-vus",
      vus: 30,
      duration: "3m",
      exec: "wsScenario"
    }
  },
  thresholds: {
    http_req_duration: ["p(95)<350"],
    http_req_failed: ["rate<0.001"]
  }
};

const API_BASE = __ENV.API_BASE || "http://localhost:8000";
const TENANT_ID = __ENV.TENANT_ID || "tenant-a";
const USERNAME = __ENV.USERNAME || "researcher";
const PASSWORD = __ENV.PASSWORD || "researcher123";
const STUDY_ID = __ENV.STUDY_ID || "study-a";
const WS_BASE = __ENV.WS_BASE || "ws://localhost:8006";

export function setup() {
  const auth = http.post(
    `${API_BASE}/auth/token`,
    JSON.stringify({ username: USERNAME, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" } }
  );
  check(auth, { "auth ok": (r) => r.status === 200 });
  return { token: auth.json("access_token") };
}

export default function (data) {
  const headers = {
    Authorization: `Bearer ${data.token}`,
    "x-tenant-id": TENANT_ID
  };

  const report = http.get(
    `${API_BASE}/reports/studies/${STUDY_ID}?page=1&page_size=25&participant_filter=p-1`,
    { headers }
  );
  check(report, { "report status": (r) => r.status === 200 });

  const templates = http.get(`${API_BASE}/reports/templates?role=researcher`, { headers });
  check(templates, { "templates status": (r) => r.status === 200 });
  sleep(0.1);
}

export function wsScenario(data) {
  const url = `${WS_BASE}/ws/studies/${STUDY_ID}?tenant_id=${TENANT_ID}&token=${data.token}`;
  const res = ws.connect(url, {}, function (socket) {
    socket.on("message", () => {});
    socket.setTimeout(function () {
      socket.close();
    }, 1500);
  });
  check(res, { "ws connected": (r) => r && r.status === 101 });
  sleep(0.2);
}
