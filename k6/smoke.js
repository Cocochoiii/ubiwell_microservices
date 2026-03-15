import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    target_2_5m_per_day: {
      executor: "constant-arrival-rate",
      rate: 30,
      timeUnit: "1s",
      duration: "2m",
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<200"],
    http_req_failed: ["rate<0.01"],
  },
};

const INGESTION_URL = __ENV.INGESTION_URL || "http://localhost:8003/events";

export default function () {
  const eventId = `evt-${__VU}-${__ITER}-${Date.now()}`;
  const payload = JSON.stringify({
    event_id: eventId,
    study_id: "study-a",
    participant_id: `p-${__VU}-${__ITER}`,
    event_type: "heart_rate",
    value: 72.4,
  });

  const params = { headers: { "Content-Type": "application/json" } };
  const res = http.post(INGESTION_URL, payload, params);
  check(res, {
    "accepted": (r) => r.status === 200,
  });
  sleep(0.01);
}
