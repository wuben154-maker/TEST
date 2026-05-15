import test from "node:test"
import assert from "node:assert"
import fs from "node:fs"
import fsp from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { resolveCicdLogSourceRefs } from "./ops-check.mjs"

function tmpDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "ops-check-cicd-"))
}

test("resolveCicdLogSourceRefs leaves explicit cloudwatch unchanged", async () => {
  const root = tmpDir()
  try {
    const cfg = {
      environment: "production",
      logSources: [
        {
          id: "cw",
          type: "cloudwatch",
          region: "ap-southeast-1",
          logGroupNames: ["/ecs/app-prod"],
        },
      ],
    }
    const out = await resolveCicdLogSourceRefs(cfg, root)
    assert.deepStrictEqual(out.logSources[0].logGroupNames, ["/ecs/app-prod"])
    assert.strictEqual(out.logSources[0].region, "ap-southeast-1")
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test("resolveCicdLogSourceRefs derives /ecs/{repository.name}-{env} when log_group empty", async () => {
  const root = tmpDir()
  try {
    const cid = path.join(root, ".cicd")
    fs.mkdirSync(path.join(cid, "env"), { recursive: true })
    await fsp.writeFile(
      path.join(cid, "env", "prod.yaml"),
      `
logging:
  cloudwatch:
    enabled: true
    region: ap-southeast-1
    log_group: ""
aws:
  region: us-east-1
`,
      "utf8",
    )
    await fsp.writeFile(
      path.join(cid, "project.yaml"),
      `
repository:
  name: secmanus
`,
      "utf8",
    )
    const cfg = {
      logSources: [
        { id: "cw", type: "cloudwatch", region: "ap-southeast-1", logGroupNames: ["${from-cicd-env}"] },
      ],
    }
    const out = await resolveCicdLogSourceRefs(cfg, root)
    assert.deepStrictEqual(out.logSources[0].logGroupNames, ["/ecs/secmanus-prod"])
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test("resolveCicdLogSourceRefs uses app when repository.name absent (deploy-aws default)", async () => {
  const root = tmpDir()
  try {
    const cid = path.join(root, ".cicd")
    fs.mkdirSync(path.join(cid, "env"), { recursive: true })
    await fsp.writeFile(
      path.join(cid, "env", "staging.yaml"),
      `
logging:
  cloudwatch:
    enabled: true
    region: eu-west-1
aws:
  region: eu-west-1
`,
      "utf8",
    )
    await fsp.writeFile(
      path.join(cid, "project.yaml"),
      `
repository:
  owner: x
`,
      "utf8",
    )
    const cfg = {
      cicdEnvironment: "staging",
      logSources: [{ id: "cw", type: "cloudwatch", region: "eu-west-1", logGroupNames: [] }],
    }
    const out = await resolveCicdLogSourceRefs(cfg, root)
    assert.deepStrictEqual(out.logSources[0].logGroupNames, ["/ecs/app-staging"])
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test("resolveCicdLogSourceRefs errors when log_group empty and .cicd/project.yaml missing", async () => {
  const root = tmpDir()
  try {
    const envDir = path.join(root, ".cicd", "env")
    fs.mkdirSync(envDir, { recursive: true })
    await fsp.writeFile(
      path.join(envDir, "prod.yaml"),
      `
logging:
  cloudwatch:
    enabled: true
    region: ap-southeast-1
    log_group: ""
`,
      "utf8",
    )
    const cfg = {
      logSources: [{ id: "cw", type: "cloudwatch", region: "${from-cicd-env}", logGroupNames: [] }],
    }
    await assert.rejects(() => resolveCicdLogSourceRefs(cfg, root), /Missing \.cicd\/project\.yaml/)
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test("resolveCicdLogSourceRefs fills from .cicd/env/prod.yaml", async () => {
  const root = tmpDir()
  try {
    const envDir = path.join(root, ".cicd", "env")
    fs.mkdirSync(envDir, { recursive: true })
    await fsp.writeFile(
      path.join(envDir, "prod.yaml"),
      `
logging:
  cloudwatch:
    enabled: true
    region: ap-southeast-1
    log_group: /ecs/from-cicd
aws:
  region: us-east-1
`,
      "utf8",
    )
    const cfg = {
      cicdEnvironment: "prod",
      logSources: [
        {
          id: "cw",
          type: "cloudwatch",
          region: "${from-cicd-env}",
          logGroupNames: [],
        },
      ],
    }
    const out = await resolveCicdLogSourceRefs(cfg, root)
    assert.deepStrictEqual(out.logSources[0].logGroupNames, ["/ecs/from-cicd"])
    assert.strictEqual(out.logSources[0].region, "ap-southeast-1")
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test("resolveCicdLogSourceRefs uses aws.region when cloudwatch.region empty", async () => {
  const root = tmpDir()
  try {
    const envDir = path.join(root, ".cicd", "env")
    fs.mkdirSync(envDir, { recursive: true })
    await fsp.writeFile(
      path.join(envDir, "prod.yaml"),
      `
logging:
  cloudwatch:
    enabled: true
    region: ""
    log_group: /g
aws:
  region: eu-west-1
`,
      "utf8",
    )
    const cfg = {
      logSources: [
        {
          id: "cw",
          type: "cloudwatch",
          region: "${from-cicd-env}",
          logGroupNames: ["${from-cicd-env}"],
        },
      ],
    }
    const out = await resolveCicdLogSourceRefs(cfg, root)
    assert.strictEqual(out.logSources[0].region, "eu-west-1")
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test("resolveCicdLogSourceRefs rejects enabled not true", async () => {
  const root = tmpDir()
  try {
    const envDir = path.join(root, ".cicd", "env")
    fs.mkdirSync(envDir, { recursive: true })
    await fsp.writeFile(
      path.join(envDir, "prod.yaml"),
      `
logging:
  cloudwatch:
    enabled: false
    region: x
    log_group: /g
`,
      "utf8",
    )
    const cfg = {
      logSources: [
        { id: "cw", type: "cloudwatch", region: "${from-cicd-env}", logGroupNames: [] },
      ],
    }
    await assert.rejects(() => resolveCicdLogSourceRefs(cfg, root), /enabled must be true/)
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test("resolveCicdLogSourceRefs rejects bad placeholder", async () => {
  const root = tmpDir()
  try {
    const cfg = {
      logSources: [
        { id: "cw", type: "cloudwatch", region: "${from-cicd_env}", logGroupNames: ["/a"] },
      ],
    }
    await assert.rejects(() => resolveCicdLogSourceRefs(cfg, root), /invalid region placeholder/)
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})
