/**
 * Fix Agent via OpenAI-compatible chat completions (e.g. ModelScope inference).
 */

import fs from "node:fs"
import path from "node:path"

function normalizeRepoRel(p) {
  return String(p ?? "")
    .trim()
    .replace(/\\/g, "/")
    .replace(/^\.?\//, "")
}

/** Same glob semantics as fix-runner.matchesGlobLit */
function matchesGlobLit(relPosix, globPat) {
  const rx =
    "^" +
    globPat
      .replace(/\\/g, "/")
      .replace(/[.+^${}()|[\]\\]/g, "\\$&")
      .replace(/\*\*/g, ".*")
      .replace(/\*/g, "[^/]*") +
    "$"
  return new RegExp(rx, "i").test(relPosix.replace(/\\/g, "/"))
}

function isInsideRepo(repoRoot, relPosix) {
  const abs = path.resolve(repoRoot, relPosix)
  const root = path.resolve(repoRoot)
  const rel = path.relative(root, abs)
  return Boolean(rel) && !rel.startsWith("..") && !path.isAbsolute(rel)
}

function stripJsonFence(txt) {
  return String(txt ?? "")
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim()
}

/**
 * @param {string} repoRoot
 * @param {string} fixRequestPath
 * @param {{
 *   baseUrl: string,
 *   apiKeyEnv: string,
 *   model?: string,
 *   temperature?: number,
 *   maxTokens?: number,
 *   timeoutMs?: number,
 *   maxContextBytesPerFile?: number,
 *   maxContextFiles?: number,
 *   maxChangedFiles?: number,
 * }} chatApi
 * @param {number} [fallbackTimeoutMs]
 */
export async function runChatCompletionsFixAgent(repoRoot, fixRequestPath, chatApi, fallbackTimeoutMs = 120_000) {
  const keyName = chatApi.apiKeyEnv
  const key = process.env[keyName]
  if (!String(key || "").trim()) {
    return {
      ok: false,
      code: "runner_deps_missing",
      message: `Missing env ${keyName} for chatApi`,
    }
  }

  let payload
  try {
    payload = JSON.parse(fs.readFileSync(fixRequestPath, "utf8"))
  } catch (e) {
    return {
      ok: false,
      code: "agent_bad_fix_request",
      message: String(e.message || e),
    }
  }

  const allowedEditPaths = Array.isArray(payload.allowedEditPaths) ? payload.allowedEditPaths.map(normalizeRepoRel).filter(Boolean) : []
  const forbiddenPayload = Array.isArray(payload.forbiddenEditPaths) ? payload.forbiddenEditPaths.map(normalizeRepoRel).filter(Boolean) : []

  if (!allowedEditPaths.length) {
    return {
      ok: false,
      code: "agent_no_allowed_paths",
      message: "fix-request allowedEditPaths empty — refusing chat fix",
    }
  }

  const maxCtxBytes = Number(chatApi.maxContextBytesPerFile ?? 100_000)
  const maxCtxFiles = Number(chatApi.maxContextFiles ?? 10)
  const maxOutFiles = Number(chatApi.maxChangedFiles ?? 8)

  /** @type {{ path: string, content: string }[]} */
  const contextBlocks = []
  const suspected = [...new Set((payload.suspectedFiles || []).map(normalizeRepoRel).filter(Boolean))].slice(
    0,
    maxCtxFiles + 5,
  )

  for (const rel of suspected) {
    if (contextBlocks.length >= maxCtxFiles) break
    if (!rel || rel.includes("..")) continue
    if (!allowedEditPaths.some((g) => matchesGlobLit(rel, g))) continue
    if (forbiddenPayload.some((g) => matchesGlobLit(rel, g))) continue
    const abs = path.join(repoRoot, rel)
    if (!fs.existsSync(abs) || !fs.statSync(abs).isFile()) continue
    try {
      const buf = fs.readFileSync(abs)
      if (buf.includes(0)) continue
      let text = buf.toString("utf8")
      if (text.length > maxCtxBytes) text = `${text.slice(0, maxCtxBytes)}\n...[truncated]\n`
      contextBlocks.push({ path: rel, content: text })
    } catch {
      /* skip */
    }
  }

  const base = String(chatApi.baseUrl || "").replace(/\/$/, "")
  const url = `${base}/chat/completions`
  const model = chatApi.model || "deepseek-ai/DeepSeek-V4-Pro"
  const timeoutMs = Number(chatApi.timeoutMs ?? fallbackTimeoutMs ?? 120_000)

  const system =
    "You fix production bugs from structured ops payloads. Reply JSON only matching this schema: " +
    '{"files":[{"path":"repo-relative/path","content":"complete new UTF-8 file contents"}]}. ' +
    "Include ONLY files you changed. If no fix is appropriate output {\"files\":[]}. " +
    "Never invent paths outside allowedEditPaths from the user message. Never output markdown."

  const userObj = {
    fixRequest: payload,
    contextFiles: contextBlocks,
    instruction:
      "Using fixRequest (especially errorSummary, stackTop, logEvidence, acceptanceCriteria), emit minimal correct edits. Paths must match allowedEditPaths globs; respect forbiddenEditPaths and forbiddenDomains.",
  }

  const body = {
    model,
    messages: [
      { role: "system", content: system },
      { role: "user", content: JSON.stringify(userObj) },
    ],
    temperature: chatApi.temperature ?? 0,
    max_tokens: Number(chatApi.maxTokens ?? 8192),
    response_format: { type: "json_object" },
  }

  const headers = { Authorization: `Bearer ${key}`, "Content-Type": "application/json" }

  const ac = new AbortController()
  const t = setTimeout(() => ac.abort(), timeoutMs)

  const postOnce = async (payload) =>
    fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: ac.signal,
    })

  let res
  try {
    res = await postOnce(body)
    if (!res.ok && res.status === 400 && body.response_format) {
      const retryBody = { ...body }
      delete retryBody.response_format
      res = await postOnce(retryBody)
    }
  } catch (e) {
    clearTimeout(t)
    const aborted = e?.name === "AbortError"
    return {
      ok: false,
      code: aborted ? "agent_http_timeout" : "agent_http_error",
      message: String(e.message || e),
    }
  }
  clearTimeout(t)

  if (!res.ok) {
    let detail = ""
    try {
      detail = (await res.text()).slice(0, 2000)
    } catch {
      /* ignore */
    }
    return {
      ok: false,
      code: `agent_http_${res.status}`,
      stderr: detail || res.statusText,
    }
  }

  let data
  try {
    data = await res.json()
  } catch {
    return { ok: false, code: "agent_bad_response", message: "chat completions response not JSON" }
  }

  const txt = data.choices?.[0]?.message?.content || ""
  let parsed
  try {
    parsed = JSON.parse(stripJsonFence(txt))
  } catch {
    return {
      ok: false,
      code: "agent_parse_failed",
      stderr: String(txt).slice(0, 4000),
    }
  }

  const files = Array.isArray(parsed.files) ? parsed.files : []
  if (files.length > maxOutFiles) {
    return {
      ok: false,
      code: "agent_too_many_files",
      message: `model returned ${files.length} files (max ${maxOutFiles})`,
    }
  }

  let wrote = 0
  for (const entry of files) {
    const rel = normalizeRepoRel(entry?.path)
    const content = entry?.content != null ? String(entry.content) : ""
    if (!rel) continue
    if (!isInsideRepo(repoRoot, rel)) {
      return { ok: false, code: "agent_path_escape", message: rel }
    }
    if (!allowedEditPaths.some((g) => matchesGlobLit(rel, g))) {
      return { ok: false, code: "agent_path_not_allowed", message: rel }
    }
    if (forbiddenPayload.some((g) => matchesGlobLit(rel, g))) {
      return { ok: false, code: "agent_path_forbidden", message: rel }
    }
    const abs = path.join(repoRoot, rel)
    fs.mkdirSync(path.dirname(abs), { recursive: true })
    fs.writeFileSync(abs, content, "utf8")
    wrote++
  }

  return {
    ok: true,
    stdout: JSON.stringify({ transport: "chat-completions", model, wrote }, null, 0),
    stderr: "",
  }
}
