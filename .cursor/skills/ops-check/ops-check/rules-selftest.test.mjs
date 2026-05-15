import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { parseYamlSubset, matchRules } from "./ops-check.mjs"
import { selftestRules } from "./lib/rules-selftest.mjs"

const __dirname = path.dirname(fileURLToPath(import.meta.url))

test("rules.yaml: every positive example hits, every negative example misses", () => {
  const raw = fs.readFileSync(path.join(__dirname, "rules.yaml"), "utf8")
  const doc = parseYamlSubset(raw)
  const fails = selftestRules(doc.rules || [])
  assert.deepEqual(fails, [], JSON.stringify(fails, null, 2))
})

test("matchRules: auth-failure exclude healthz", () => {
  const raw = fs.readFileSync(path.join(__dirname, "rules.yaml"), "utf8")
  const doc = parseYamlSubset(raw)
  const rules = (doc.rules || []).filter((r) => r.name === "auth-failure")
  const stack = "unknown-frame"
  const h1 = matchRules('GET /healthz 401 Unauthorized', rules, { stackTop: stack })
  assert.equal(h1.length, 0)
  const h2 = matchRules("GET /api/users 401 Unauthorized", rules, { stackTop: stack })
  assert.equal(h2.length, 1)
})
