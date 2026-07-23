// Minimal, dependency-free Chrome DevTools Protocol client.
//
// Uses Node 22's built-in global `WebSocket` and `fetch`, plus a locally
// launched system Chrome (`/usr/bin/google-chrome`). No npm packages.
//
// Exposes: launchChrome(), CDPSession (send/on), and a small helper to read
// the DevToolsActivePort file Chrome writes on startup.
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = process.env.CHROME_BIN || "/usr/bin/google-chrome";

export async function launchChrome() {
  const userDataDir = mkdtempSync(join(tmpdir(), "vr-chrome-"));
  const args = [
    "--headless=new",
    "--remote-debugging-port=0",
    `--user-data-dir=${userDataDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--hide-scrollbars",
    "--disable-extensions",
    "--disable-background-networking",
    "--force-color-profile=srgb",
    "about:blank",
  ];
  const proc = spawn(CHROME, args, { stdio: ["ignore", "ignore", "pipe"] });
  let stderr = "";
  proc.stderr.on("data", (d) => (stderr += d.toString()));

  // Chrome writes the chosen port to <user-data-dir>/DevToolsActivePort.
  const portFile = join(userDataDir, "DevToolsActivePort");
  const port = await waitFor(async () => {
    if (existsSync(portFile)) {
      const line = readFileSync(portFile, "utf8").split("\n")[0].trim();
      if (line) return Number(line);
    }
    if (proc.exitCode !== null)
      throw new Error(`Chrome exited early (${proc.exitCode}):\n${stderr}`);
    return null;
  }, 15000);

  const verRes = await fetch(`http://127.0.0.1:${port}/json/version`);
  const { webSocketDebuggerUrl } = await verRes.json();

  return {
    proc,
    port,
    webSocketDebuggerUrl,
    userDataDir,
    async close() {
      try { proc.kill("SIGKILL"); } catch {}
      try { rmSync(userDataDir, { recursive: true, force: true }); } catch {}
    },
  };
}

// One websocket connection, multiplexed across a browser target + attached
// page session (flatten mode: every message carries an optional sessionId).
export class CDP {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    this.listeners = new Map();
    ws.addEventListener("message", (ev) => this._onMessage(ev.data));
  }

  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((resolve, reject) => {
      ws.addEventListener("open", resolve, { once: true });
      ws.addEventListener("error", () => reject(new Error("ws error")), { once: true });
    });
    return new CDP(ws);
  }

  _onMessage(data) {
    const msg = JSON.parse(data);
    if (msg.id !== undefined && this.pending.has(msg.id)) {
      const { resolve, reject } = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      if (msg.error) reject(new Error(`${msg.error.message} (${JSON.stringify(msg.params || {})})`));
      else resolve(msg.result);
    } else if (msg.method) {
      const key = msg.sessionId ? `${msg.sessionId}:${msg.method}` : msg.method;
      const cbs = this.listeners.get(key);
      if (cbs) for (const cb of cbs) cb(msg.params);
    }
  }

  send(method, params = {}, sessionId) {
    const id = ++this.id;
    const payload = { id, method, params };
    if (sessionId) payload.sessionId = sessionId;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify(payload));
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`CDP timeout: ${method}`));
        }
      }, 45000);
    });
  }

  on(method, cb, sessionId) {
    const key = sessionId ? `${sessionId}:${method}` : method;
    if (!this.listeners.has(key)) this.listeners.set(key, new Set());
    this.listeners.get(key).add(cb);
  }
  off(method, cb, sessionId) {
    const key = sessionId ? `${sessionId}:${method}` : method;
    this.listeners.get(key)?.delete(cb);
  }

  once(method, sessionId, timeout = 30000) {
    return new Promise((resolve, reject) => {
      const cb = (params) => { this.off(method, cb, sessionId); resolve(params); };
      this.on(method, cb, sessionId);
      setTimeout(() => { this.off(method, cb, sessionId); reject(new Error(`event timeout: ${method}`)); }, timeout);
    });
  }

  close() { try { this.ws.close(); } catch {} }
}

async function waitFor(fn, timeoutMs) {
  const start = Date.now();
  for (;;) {
    const v = await fn();
    if (v !== null && v !== undefined) return v;
    if (Date.now() - start > timeoutMs) throw new Error("waitFor timed out");
    await new Promise((r) => setTimeout(r, 100));
  }
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
