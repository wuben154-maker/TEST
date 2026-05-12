#!/usr/bin/env node
/**
 * Local-only: POST /auth/login then print a dev URL with a one-time hash bootstrap.
 * Opening that URL in a browser (or browse automation) sets auth_token / auth_user and reloads.
 *
 * Env (or root .env / .env.local, simple KEY=value lines):
 *   E2E_EMAIL / LOCAL_AUTH_EMAIL
 *   E2E_PASSWORD / LOCAL_AUTH_PASSWORD
 *   E2E_API_BASE (default http://127.0.0.1:8000)
 *   LOCAL_AUTH_FRONTEND_URL (default http://127.0.0.1:8080 — match vite.config server.port)
 */

import { readFileSync, existsSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");

function loadEnvFile(name) {
  const p = join(root, name);
  if (!existsSync(p)) {
    return {};
  }
  const out = {};
  for (const line of readFileSync(p, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const eq = trimmed.indexOf("=");
    if (eq <= 0) {
      continue;
    }
    const key = trimmed.slice(0, eq).trim();
    let v = trimmed.slice(eq + 1).trim();
    if (
      (v.startsWith('"') && v.endsWith('"')) ||
      (v.startsWith("'") && v.endsWith("'"))
    ) {
      v = v.slice(1, -1);
    }
    out[key] = v;
  }
  return out;
}

const fileEnv = { ...loadEnvFile(".env"), ...loadEnvFile(".env.local") };
const env = { ...fileEnv, ...process.env };

const apiBase = (env.E2E_API_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
const email = env.E2E_EMAIL || env.LOCAL_AUTH_EMAIL;
const password = env.E2E_PASSWORD || env.LOCAL_AUTH_PASSWORD;
const front = (env.LOCAL_AUTH_FRONTEND_URL || "http://127.0.0.1:8080").replace(
  /\/$/,
  "",
);

if (!email || !password) {
  console.error(
    "Missing credentials. Set E2E_EMAIL + E2E_PASSWORD (or LOCAL_AUTH_EMAIL + LOCAL_AUTH_PASSWORD) in env or .env / .env.local",
  );
  process.exit(1);
}

const res = await fetch(`${apiBase}/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, password }),
});

if (!res.ok) {
  const text = await res.text();
  console.error(`Login failed HTTP ${res.status}: ${text.slice(0, 500)}`);
  process.exit(1);
}

const body = await res.json();
const payload = JSON.stringify({
  access_token: body.access_token,
  user: body.user,
});
const b64 = Buffer.from(payload, "utf8").toString("base64");
const url = `${front}/#__secmanus_bootstrap=${encodeURIComponent(b64)}`;

console.log(url);
console.error(
  "\nOpen the URL above in your browser (or pass it to browse automation). DEV only; clears hash after apply.\n",
);
