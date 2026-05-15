import assert from "node:assert"
import fsp from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { readState, writeState } from "./ops-check.mjs"

test("readState normalizes missing llmVerdicts to {}", async () => {
  const dir = await fsp.mkdtemp(path.join(os.tmpdir(), "ops-llm-state-"))
  const sf = path.join(dir, "state.json")
  await fsp.writeFile(sf, JSON.stringify({ cursors: {}, fingerprints: {} }), "utf8")
  const s = await readState(sf)
  assert.deepStrictEqual(s.llmVerdicts, {})
})

test("writeState persists llmVerdicts key", async () => {
  const dir = await fsp.mkdtemp(path.join(os.tmpdir(), "ops-llm-state-"))
  const sf = path.join(dir, "state.json")
  const base = await readState(sf)
  base.llmVerdicts = { abcd: { severity: "low", autofix: false, ts: 1, ttlMs: 1000, model: "m" } }
  await writeState(sf, base, { canWriteState: true })
  const raw = JSON.parse(await fsp.readFile(sf, "utf8"))
  assert.ok(Object.prototype.hasOwnProperty.call(raw, "llmVerdicts"))
})
