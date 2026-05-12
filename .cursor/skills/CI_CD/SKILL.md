---
name: aws-cicd
description: |
  Single-entry AWS CI/CD installer for GitHub projects. Use when the user wants
  to add automated CI, release, AWS deployment, verification, and rollback to a
  GitHub repository. Supports AWS US regions, ECS/Fargate by default, optional
  EC2 SSH deployment, and single-node or distributed modes.
---

# AWS CI/CD

## Purpose

Install a compact AWS CI/CD system into a target GitHub repository. The installed workflows build, release, deploy, verify, and roll back applications on AWS.

This is the only CI/CD skill entrypoint. Do not route AWS CI/CD work to legacy split-stage skills.

## When To Use

Use this skill when the user asks to:

- add CI/CD to a GitHub project
- deploy an application to AWS
- install GitHub Actions for CI, release, deploy, verification, and rollback
- support `single-node` or `distributed` deployment modes
- deploy to ECS/Fargate or explicitly to EC2 over SSH

Start from `github_repo_url`. Do not ask the user to manually download the target repository first.

## Inputs

Required:

- `github_repo_url`: target GitHub repository URL.
- `environment`: `dev | staging | prod`.
- `deployment_mode`: `single-node | distributed`.

Optional:

- `deployment_target`: `ecs | ec2-ssh`, default `ecs`.
- `service_scope`: `frontend-only | backend-only | worker-only | all`, default inferred.
- `aws_region`: default `us-east-1`; `us-west-2` is also acceptable for US workloads.
- `install_branch`: default `aws-cicd-setup`.
- `open_pr`: default `false`; only create a PR when the user explicitly asks.

## Non-Negotiable Rules

- Keep one CI/CD entrypoint: `.cursor/skills/CI_CD/SKILL.md`.
- Inspect the target repo before asking the user for configuration.
- Only ask for secrets and cloud resource identifiers that cannot be safely inferred.
- Never write real secret values to repository files.
- Store only secret names, variable names, or ARN references in `.cicd/env/<environment>.yaml`.
- Default to ECS/Fargate in US regions.
- Treat EC2 SSH as an explicit fallback or transition path.
- `single-node` is not high availability.
- `distributed` requires ECS desired count `>= 2` or at least two EC2 hosts.
- Build once, push once, and deploy immutable ECR image digests.
- Deployment success is not release success. Verification is the final gate.
- Failed verification must roll back automatically when rollback is possible, otherwise block exposure and emit evidence.

## Execution Flow

1. Use `gh` to read target GitHub metadata when available.
2. Clone or check out `github_repo_url` into a temporary or user-approved path.
3. Inspect repository structure, commands, Dockerfiles, ports, health checks, database migrations, and existing automation.
4. Produce an auto-detection summary and write detected values into `.cicd/project.yaml`.
5. Stop and ask before overwriting an existing CI/CD system.
6. Render templates from `.cursor/skills/CI_CD/templates/`.
7. Install target repo files on `install_branch`.
8. Report required GitHub Secrets, GitHub Variables, and AWS secret store entries.
9. Ask before committing, pushing, or opening a PR.
10. When configured, run `ci.yml`, then `release.yml`, then `deploy-aws.yml`.
11. Verify health checks, target health, and smoke checks.
12. Roll back failed deployments or failed verification when rollback metadata exists.

## Auto-Detection Contract

Auto-read:

- Git metadata: owner, repository, default branch, current branch, remote URL.
- Layout: single app, split frontend/backend, monorepo, worker, shared packages.
- Runtime markers: lockfiles, `package.json`, `pyproject.toml`, `requirements.txt`, `go.mod`, `pom.xml`, `build.gradle`, `Dockerfile`, `docker-compose.yml`, `turbo.json`.
- Commands: install, lint, typecheck, test, build, start.
- Docker context, Dockerfile path, image name hints, container names.
- Ports from Docker `EXPOSE`, `.env.example`, config files, and framework defaults.
- Health checks from Docker healthcheck, existing routes, `/health`, `/api/health`, and `/`.
- Database migration tooling such as Prisma, Drizzle, Flyway, Liquibase, Django migrations, or Alembic.
- Existing `.github/workflows`, `.cicd`, and README deployment notes.

Infer but present for confirmation:

- service roles and `service_scope`
- container names
- build contexts
- health check paths
- initial ECS desired counts
- EC2 host roles for distributed deployments

## Generated Target Files

Install this layout into the target repository:

```text
.github/workflows/
  ci.yml
  release.yml
  deploy-aws.yml

.cicd/
  project.yaml
  env/
    dev.yaml.example
    staging.yaml.example
    prod.yaml.example
  secrets/
    README.md
  runbooks/
    rollback.md
```

Users copy an environment example before deployment:

```text
cp .cicd/env/prod.yaml.example .cicd/env/prod.yaml
```

## Manual Configuration Boundary

Only ask the user to fill or confirm:

- AWS account ID and final region.
- GitHub OIDC role ARN secret name.
- ECR repository names.
- ECS cluster name, service names, task families, execution roles, task roles, subnets, security groups, ALB, and target groups.
- EC2 hosts, SSH user, and SSH key secret name.
- Domains, certificate references, runtime secret names, database credential secret names, and third-party API secret names.

Manual values live in:

- `.cicd/env/<environment>.yaml`
- `.cicd/secrets/README.md`
- GitHub Secrets and Variables
- AWS Secrets Manager or SSM Parameter Store

Do not generate separate `.cicd/aws/ecs.yaml` or `.cicd/aws/ec2.yaml` unless a future multi-environment reuse problem justifies it.

## Deployment Modes

`single-node`:

- ECS desired count is `1`.
- EC2 deploys to the primary host only.
- Suitable for development, staging, and small apps.

`distributed`:

- ECS desired count is `2` or more.
- EC2 requires at least two hosts or explicit host roles.
- Suitable for production or high-availability staging.

## AWS Targets

`ecs` is the default:

- Builds and pushes ECR images by immutable digest.
- Registers a new task definition revision from the current running task definition.
- Updates ECS services.
- Waits for service stability.
- Verifies ALB target health and HTTP health checks.
- Rolls back to the previous task definition on failed verification.

`ec2-ssh` is optional:

- Pulls immutable ECR images on selected EC2 hosts.
- Records the currently running image digest as rollback baseline.
- Restarts containers over SSH.
- Verifies every selected host.
- Restores the previous digest when verification fails.

## Verification And Rollback

The installed pipeline must produce:

- CI summary for lint, typecheck, tests, build, and skipped checks with reasons.
- Release metadata with commit SHA, image URI, digest, actor, run URL, and release ID.
- Deployment evidence with environment, service revisions, target health, HTTP verification, and workflow URL.
- Verification result: `success | failed | blocked`.
- Rollback evidence when rollback runs.

Rollback is automatic for:

- ECS service update followed by failed verify.
- EC2 container restart followed by failed verify.
- ALB target health failure.
- HTTP health check failure.

Human intervention is required for:

- destructive database migrations
- missing AWS permissions
- missing secrets
- broken network infrastructure

## Stop Conditions

Stop and ask before proceeding when:

- Existing CI/CD files would be overwritten.
- Production deploy is requested but required AWS identifiers are missing.
- A user asks to bypass failed tests or security checks.
- Real secrets are about to be written to repository files.
- `distributed` is selected without ECS capacity settings or at least two EC2 hosts.
- Deployment would use mutable image tags instead of immutable digests.

## Output Report

Return a concise setup report:

- target repo and branch
- detected services, commands, ports, health paths, and migration tooling
- files installed, skipped, or blocked
- manual AWS/GitHub values still required
- next GitHub Actions workflow to run
- rollback path and evidence location
