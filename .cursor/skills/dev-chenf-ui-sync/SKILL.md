---
name: dev-chenf-ui-sync
description: Phase A→B→C — push UI work, merge into dev-for-master and push, then **mandatory** Phase C merges `origin/dev-for-master` into local `dev-chenf-ui` **and** `git push origin dev-chenf-ui` so remote UI matches. Use for "/dev-chenf-ui-sync".
---

# dev-chenf-ui → origin → dev-for-master → **Phase C（必选）**

## Branches (fixed for this workspace)

| Role | Branch |
|------|--------|
| UI work | `dev-chenf-ui` |
| Integration / pre-master | `dev-for-master` |
| Remote | `origin` |

If the user renames branches, replace names consistently in commands below.

**Full run order:** **Phase A** → **Phase B** → **Phase C**（C **必选**：含 **merge `origin/dev-for-master` 进本地 `dev-chenf-ui`** + **`git push origin dev-chenf-ui`**）。B 成功 `push origin dev-for-master` 之后才进入 C。若 Phase B 失败或未 push，**不要**执行 Phase C。

## Golden rules

| Rule | Detail |
|------|--------|
| **No local junk in commits** | Do **not** stage secrets or personal artifacts: `.env`, `*.pem`, keys, `**/.vscode/chrome-debug-profile/**`, other paths in **`.gitignore`** / **`AGENT.md`** / **delivery-pipeline GR-SECRETS**. |
| **Explicit staging** | Prefer `git add <path> …` per touch list. Avoid `git add -A` unless the user insists **and** `git status` + `git diff --cached` were reviewed. |
| **No surprise force-push** | Never `git push --force` unless the user **explicitly** requests it. |
| **Verify before push** | After staging: `git diff --cached` (no credentials, no accidental local-only files). |

## Phase A — Local `dev-chenf-ui` → `origin/dev-chenf-ui`

1. `git fetch origin`
2. `git checkout dev-chenf-ui`
3. If tracking is missing: `git branch -u origin/dev-chenf-ui dev-chenf-ui` (when `origin/dev-chenf-ui` already exists).
4. `git status` — note modified / untracked; **do not** add excluded paths.
5. Stage **only** intended project files (explicit paths). Re-run `git diff --cached`.
6. If there is nothing to commit, skip to step 8.
7. Commit (**English** message, conventional or `feat:` / `fix:` / `checkpoint:` as user prefers):
   ```bash
   git commit -m "feat(ui): <short summary>"
   ```
8. Push:
   ```bash
   git push origin dev-chenf-ui
   ```

## When `dev-for-master` already moved (others pushed)

**Normal:** teammates commit to `origin/dev-for-master` between your runs. **Phase B step 3 (`git pull origin dev-for-master`) is mandatory every time** before you merge `origin/dev-chenf-ui`. Omitting it rebases your merge onto an stale tip and causes harder conflicts or a rejected push.

**Preflight (after `git fetch origin`):**

```bash
# Commits on remote integration you do not have locally yet
git log --oneline dev-for-master..origin/dev-for-master
```

- Output empty → local `dev-for-master` matches remote (after fetch), or you never fetched; still run step 3 for safety.
- Output non-empty → pull will bring those commits in; expect a merge or fast-forward, then proceed.

**If local `dev-for-master` has commits that are not on `origin/dev-for-master`** (`git log origin/dev-for-master..dev-for-master` shows commits): push or coordinate **before** merging UI from another machine; do not assume you are the only integrator.

**Optional — integrate `dev-for-master` into `dev-chenf-ui` first (recommended when integration is busy):** resolve conflicts and run checks on the UI branch, then merge a tested `origin/dev-chenf-ui` into fresh `dev-for-master`.

1. `git fetch origin`
2. `git checkout dev-chenf-ui`
3. `git merge origin/dev-for-master` — or `git rebase origin/dev-for-master` if the team wants a linear UI branch (force-push rules apply for rebase).
4. Fix conflicts, run tests if applicable, `git push origin dev-chenf-ui`
5. Run **Phase B** from the top (fetch, checkout `dev-for-master`, pull, merge `origin/dev-chenf-ui`, push).

## Phase B — Remote `dev-chenf-ui` → `dev-for-master`

1. `git fetch origin`
2. `git checkout dev-for-master`
3. **Always** update local `dev-for-master` from remote (picks up others’ commits):
   ```bash
   git pull origin dev-for-master
   ```
   - Default `pull` uses merge; if `dev-for-master` is configured with `pull.rebase` true, you get a rebase pull instead — both are fine if the branch policy allows it.
   - If Git reports conflicts during **this** pull, resolve them, complete the pull, **then** continue to step 4.
4. Merge **remote** UI branch into `dev-for-master`:
   ```bash
   git merge origin/dev-chenf-ui -m "merge: dev-chenf-ui into dev-for-master"
   ```
   - If the team prefers merging the local tracking branch after a fresh pull: `git merge dev-chenf-ui` is equivalent **only if** local `dev-chenf-ui` matches `origin/dev-chenf-ui` (verify with `git log -1 dev-chenf-ui origin/dev-chenf-ui`).
5. Resolve conflicts if any; run quick sanity checks if the repo documents them (tests optional unless user asked).
6. Push:
   ```bash
   git push origin dev-for-master
   ```
7. **Continue to Phase C** — required after a successful step 6.

## Phase C — 合回本地 `dev-chenf-ui`（**必选**）

**Why:** Phase **A+B** only move *your UI commits* into `dev-for-master`. Without Phase **C**, **local `dev-chenf-ui` stays behind** `origin/dev-for-master` (others' commits, merge commit, conflict resolutions). **C 还必须把合并后的 `dev-chenf-ui` 推到 `origin`**：否则 **`origin/dev-chenf-ui` 仍停在合并前**，与别人/Cursor 看到的「已合入集成」不一致。**本 skill 要求 B 成功后跑完整个 C（merge + push UI），缺一不可。**

### 目标澄清

| 你想要 | 做法 |
|--------|------|
| **继续用 `dev-chenf-ui` 开发，且工作区 = 集成分支最新代码** | **Phase C1** — 默认 |
| **人就在集成分支上干活** | A+B 后可 `checkout dev-for-master` + `pull`；若继续用 `dev-chenf-ui`，**仍须 C1** |
| **reset 对齐（危险，须用户明确要求）** | `git reset --hard origin/dev-for-master`；勿默认强推 |

### Phase C1 — merge（默认）

**前提：** Phase **B** 已成功 **`git push origin dev-for-master`**。若 B 失败、中止或未 push，**不得**执行 Phase C。

1. `git fetch origin`
2. `git checkout dev-chenf-ui`
3. `git merge origin/dev-for-master -m "merge: sync dev-for-master into dev-chenf-ui"`
4. 若有冲突 → 解决后完成合并（**ours = dev-chenf-ui**，**theirs = 集成侧**，比照 **§ Merge conflicts**）。
5. **`git push origin dev-chenf-ui`（必选）** — 把 **含合并提交** 的本地 `dev-chenf-ui` 同步到远程；**不做这一步则 `origin/dev-chenf-ui` 与本地不一致**。若 **non-fast-forward** → **§ If something fails**，与团队协调，`pull`/`merge` 后再推，**勿**默认 `git push --force`。
6. 可选：`git fetch origin` 后确认 `dev-chenf-ui` 与 `origin/dev-chenf-ui` 指向同一提交（`git rev-parse dev-chenf-ui origin/dev-chenf-ui`）。
7. 无未提交修改时校验目录树：`git diff --stat origin/dev-for-master HEAD`（无输出 ≈ 与集成树一致）。

### Phase C — 工作区 / stash

切回 `dev-chenf-ui` 后、**C1 步骤 3 之前** `git stash pop`（若 Phase B 使用过 stash）。**不要** stash `.env`。

## Merge conflicts (Phase B: `dev-for-master` ← `origin/dev-chenf-ui`)

Git stops the merge when the **same lines** changed on both branches. **Current branch** during the merge is **`dev-for-master`** (the branch you checked out). The incoming branch is **`origin/dev-chenf-ui`**.

### 1. See what is blocked

```bash
git status
```

Look for **“both modified”** / **Unmerged paths**. List only names:

```bash
git diff --name-only --diff-filter=U
```

### 2. Open each conflicted file

Conflict regions look like:

```text
<<<<<<< HEAD
# code as on dev-for-master (current checkout)
=======
# code as on dev-chenf-ui (incoming)
>>>>>>> origin/dev-chenf-ui
```

- **Edit** the file to the **final** content you want: remove **all** marker lines (`<<<<<<<`, `=======`, `>>>>>>>`).  
- **Never** commit files that still contain those markers.

### 3. Choose intent (manual vs one-sided)

| Goal | Approach |
|------|----------|
| **Blend both** (normal) | Edit the region so the result matches product intent; delete markers. |
| **Keep integration branch version for this file** | For that file only: `git checkout --ours -- path/to/file` then re-open and verify (ours = `dev-for-master` during this merge). |
| **Take UI branch version for this file** | For that file only: `git checkout --theirs -- path/to/file` then verify (theirs = `origin/dev-chenf-ui` during this merge). |

**Caution:** `--ours` / `--theirs` replace the **whole file** from that side. Use only when you are sure one branch should win entirely for that path.

### 4. Mark resolved and finish the merge

```bash
git add path/to/resolved-file …
# repeat until: git diff --name-only --diff-filter=U  → empty

git status   # should say all conflicts fixed

git commit   # completes the merge (editor opens; or use -m "merge: resolve conflicts with dev-chenf-ui")
git push origin dev-for-master
```

If Git already created a merge commit message, `git commit` without `-m` is fine.

### 5. Abort if you need to start over

Only if **no** resolution has been committed yet:

```bash
git merge --abort
```

This returns `dev-for-master` to the state **before** `git merge origin/dev-chenf-ui`.

### 6. Special cases

- **`.env` / secrets in conflict:** Do **not** resolve by pasting real keys into the repo. Keep `.env` out of commits; align on **`.env.example`** or config docs; use local `.env` only on disk.  
- **`package-lock.json` / large generated files:** Prefer regenerating per team practice (e.g. resolve `package.json` manually, then `npm install` and commit the new lockfile **if** the team commits lockfiles).  
- **Binary files:** Git cannot merge; pick one version (`--ours` / `--theirs`) or replace the file manually, then `git add`.

### 7. Phase C merge conflicts (`dev-chenf-ui` ← `origin/dev-for-master`)

If **Phase C1** conflicts: **current branch = `dev-chenf-ui`**, incoming = integration. **`--ours`** = `dev-chenf-ui`, **`--theirs`** = `origin/dev-for-master`. Resolve like **§§ 1–4** above, then `git commit`, run **C1 step 5** (`git push origin dev-chenf-ui`), and **§7** tree check.

## If something fails

- **Push rejected (non-fast-forward)** on `dev-chenf-ui`: user must pull/rebase on that branch or coordinate; do not force-push by default.
- **Push rejected (non-fast-forward)** on `dev-for-master`: remote moved. Run `git fetch origin && git pull origin dev-for-master`, resolve pull conflicts if any. Confirm UI is still merged: `git merge-base --is-ancestor origin/dev-chenf-ui dev-for-master`; if that exits **non-zero**, run `git merge origin/dev-chenf-ui` again, then push. Repeat fetch/pull if the remote moves again before push succeeds.
- **Merge conflicts:** follow **§ Merge conflicts** (Phase B **or** Phase C §7); then push the branch you were merging on.
- **Dirty tree** with unwanted local files: `git restore --staged <path>` / `git restore <path>`; never commit `.env` to fix conflicts.

## Coordination

- Full **`docs/Process/<slug>/`** delivery with Phase 7 gates → prefer **`.cursor/skills/delivery-pipeline/SKILL.md`** for the **verified** commit message + `passed/…` tag on that slug’s touch list; this skill is for **branch promotion** (UI branch + integration branch), not a substitute for delivery sign-off.
- When **`dev-for-master` is high-churn**, use **§ When `dev-for-master` already moved** (preflight + optional UI-first merge) to avoid stale bases and repeated push rejections.
- **Phase C is mandatory** after a successful Phase B push; see **§ Phase C** and **Full run order** at top.

## References

- **`AGENT.md`** — Local checkpoint commits, secret hygiene.
- **`.cursor/skills/delivery-pipeline/SKILL.md`** — Phase 7 auto-commit when applicable.
