import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import test from "node:test";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

async function readJavaScript(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const contents = await Promise.all(entries.map(async (entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return readJavaScript(path);
    if (!entry.isFile() || !entry.name.endsWith(".js")) return "";
    return readFile(path, "utf8");
  }));
  return contents.flat(Infinity).join("\n");
}

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(new Request("http://localhost/", { headers: { accept: "text/html" } }), {
    ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) },
  }, { waitUntil() {}, passThroughOnException() {} });
}

test("renders the designer PDF preflight product", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /PrintReady/);
  assert.match(html, /交付印厂之前/);
  assert.match(html, /开始印前诊断/);
  assert.match(html, /不伪造 300 PPI/);
  assert.doesNotMatch(html, /codex-preview|Your site is taking shape|react-loading-skeleton/i);
});

test("production client targets the hosted PDF API", async () => {
  const clientJavaScript = await readJavaScript(join(frontendRoot, "dist", "client"));
  assert.match(clientJavaScript, /https:\/\/ai-print-production-os-api\.onrender\.com/);
  assert.doesNotMatch(clientJavaScript, /https?:\/\/(?:127\.0\.0\.1|localhost):8000/);
});
