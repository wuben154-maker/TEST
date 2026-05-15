/**
 * Isolation / diff gate unit checks (fix-runner safety helpers).
 */
import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import { assertBoundedDiffGate, isInsideGitRepo } from "./lib/fix-runner.mjs"

function git(args, cwd) {
  const r = spawnSync("git", args, { cwd, encoding: "utf8" })
  assert.equal(r.status, 0, `${args.join(" ")} stderr=${r.stderr}`)
}

function initScratchRepo(dir) {
  git(["init"], dir)
  git(["config", "user.email", "ops-fixture@localhost"], dir)
  git(["config", "user.name", "ops-fixture"], dir)
  fs.writeFileSync(path.join(dir, "a.txt"), "a\n", "utf8")
  git(["add", "a.txt"], dir)
  git(["commit", "-m", "init"], dir)
}

test("assertBoundedDiffGate ok for bounded text change inside allowlist", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wt-ops-diff-"))
  initScratchRepo(dir)
  fs.writeFileSync(path.join(dir, "a.txt"), "b\n", "utf8")

  const g = assertBoundedDiffGate({
    repoRoot: dir,
    allowedEditPaths: ["a.txt"],
    forbiddenEditPaths: [],
    maxDiffLines: 400,
    maxChangedFiles: 8,
  })
  assert.equal(g.ok, true, JSON.stringify(g))
})

test("assertBoundedDiffGate fails when change is outside allowed globs", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wt-ops-diff-forbid-"))
  initScratchRepo(dir)
  fs.writeFileSync(path.join(dir, "a.txt"), "b\n", "utf8")

  const g = assertBoundedDiffGate({
    repoRoot: dir,
    allowedEditPaths: ["z/**"],
    forbiddenEditPaths: [],
    maxDiffLines: 400,
    maxChangedFiles: 8,
  })
  assert.equal(g.ok, false)
  assert.ok(String(g.reason || "").startsWith("outside_allowed"))
})

test("assertBoundedDiffGate fails on forbidden glob hit", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wt-ops-diff-forbidp-"))
  initScratchRepo(dir)
  fs.writeFileSync(path.join(dir, "a.txt"), "b\n", "utf8")

  const g = assertBoundedDiffGate({
    repoRoot: dir,
    allowedEditPaths: ["**"],
    forbiddenEditPaths: ["a.txt"],
    maxDiffLines: 400,
    maxChangedFiles: 8,
  })
  assert.equal(g.ok, false)
  assert.ok(String(g.reason || "").startsWith("forbidden_hit"))
})

test("isInsideGitRepo false without git metadata", () => {
  const empty = fs.mkdtempSync(path.join(os.tmpdir(), "wt-ops-nogit-"))
  assert.equal(isInsideGitRepo(empty), false)
})
