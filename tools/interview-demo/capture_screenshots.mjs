import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { chromium } from "playwright";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const OUTPUT_DIR = path.resolve(__dirname, "../../docs/perf/screenshots");

async function screenshotPublicPage(browser, url, outputFile) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  await page.goto(url, { waitUntil: "networkidle", timeout: 45000 });
  await page.screenshot({ path: outputFile, fullPage: true });
  await page.close();
}

async function screenshotGrafana(browser, outputFile) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  await page.goto("http://localhost:3000/login", { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.fill('input[name="user"]', "admin");
  await page.fill('input[name="password"]', "admin");
  await page.click('button[type="submit"]');

  // Optional password-change screen handling.
  if (page.url().includes("/password")) {
    await page.fill('input[name="newPassword"]', "admin");
    await page.fill('input[name="confirmNew"]', "admin");
    await page.click('button[type="submit"]');
  }

  await page.goto("http://localhost:3000/d/ubiwell-platform-overview", {
    waitUntil: "networkidle",
    timeout: 45000
  });
  await page.screenshot({ path: outputFile, fullPage: true });
  await page.close();
}

async function main() {
  await mkdir(OUTPUT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });

  try {
    await screenshotPublicPage(browser, "http://localhost:8000/docs", path.join(OUTPUT_DIR, "api-docs.png"));
    await screenshotPublicPage(browser, "http://localhost:5173", path.join(OUTPUT_DIR, "web-dashboard.png"));
    await screenshotPublicPage(browser, "http://localhost:9090", path.join(OUTPUT_DIR, "prometheus.png"));
    await screenshotPublicPage(browser, "http://localhost:16686", path.join(OUTPUT_DIR, "jaeger.png"));
    await screenshotGrafana(browser, path.join(OUTPUT_DIR, "grafana-overview.png"));
  } finally {
    await browser.close();
  }

  console.log(`Saved screenshots to ${OUTPUT_DIR}`);
}

main().catch((err) => {
  console.error("Screenshot capture failed:", err);
  process.exit(1);
});
