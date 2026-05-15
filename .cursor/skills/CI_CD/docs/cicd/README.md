# AWS CI/CD Skill

This repository provides one compact Cursor skill for installing AWS CI/CD automation into a target GitHub repository.

## Goal

- Keep one CI/CD entrypoint: `.cursor/skills/aws-cicd/SKILL.md`.
- Start from a `github_repo_url`; do not require the user to download the target repo manually.
- Inspect the target repo before asking for configuration.
- Generate real GitHub Actions for CI, release, AWS deploy, verification, and rollback.
- Support AWS US regions, defaulting to ECS/Fargate.
- Preserve EC2 SSH as an explicit fallback or transition path.
- Support `single-node` and `distributed` deployment modes.
- Keep user-fillable values in one target repo config directory.

Legacy CI/CD skills are intentionally removed from the operating model. Their useful behavior is folded into the single `aws-cicd` skill, templates, and this document.

## Installed Target Structure

The skill installs this structure into the target application repository:

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

Users copy the environment they need before deploy:

```text
cp .cicd/env/prod.yaml.example .cicd/env/prod.yaml
```

Real secrets never go into these files.

## Auto-Detection

The skill must inspect the target GitHub repository and write results to `.cicd/project.yaml`.

Auto-detected fields include:

- GitHub owner, repo, default branch, current branch, and remote URL.
- Project layout: single app, frontend/backend split, monorepo, worker, shared packages.
- Service roles: `frontend`, `backend`, `worker`, `shared`.
- Package manager and runtime markers.
- Install, lint, typecheck, test, build, and start commands.
- Dockerfiles, build contexts, Docker Compose files, container names, and ports.
- Health checks from Docker, known routes, `/health`, `/api/health`, or `/`.
- Database migration tooling such as Prisma, Drizzle, Flyway, Liquibase, Django migrations, or Alembic.
- Existing `.github/workflows`, `.cicd`, and deployment notes.

The generated `.cicd/project.yaml` is machine-maintained. Users normally do not edit it.

## Manual Configuration

Only ask the user for values that cannot be safely inferred:

- AWS account ID.
- AWS region, default `us-east-1`.
- GitHub OIDC role ARN secret name.
- ECR repository names.
- ECS cluster name, service names, task families, execution roles, task roles, ALB target groups, VPC, subnets, and security groups.
- EC2 hosts, SSH user, and SSH private key secret name.
- Domains, certificate references, runtime secret names, database credential secret names, and third-party API secret names.

These values live in `.cicd/env/<environment>.yaml` and `.cicd/secrets/README.md`. Do not split ECS and EC2 into separate `.cicd/aws/*.yaml` files unless future cross-environment reuse creates real complexity.

## Secret Boundary

Commit only secret names, variable names, and ARN references.

Use:

- GitHub Secrets for `AWS_RELEASE_ROLE_ARN` and `AWS_EC2_SSH_PRIVATE_KEY`.
- GitHub Variables for optional defaults such as `AWS_REGION` and ECR repository names.
- AWS Secrets Manager or SSM Parameter Store for application runtime secrets, database credentials, and third-party API keys.

Do not commit `.env`, private keys, cloud credential files, production secret values, or generated debug profiles.

## Deployment Models

`single-node`:

- ECS desired count is `1`.
- EC2 deploys to one primary host.
- Suitable for development, small staging, and small apps.
- Must not be described as high availability.

`distributed`:

- ECS desired count is `2` or more.
- EC2 requires at least two hosts or explicit host roles.
- Suitable for production or high-availability staging.
- Production should also define autoscaling or an explicit capacity policy.

## AWS Targets

ECS/Fargate is the default:

- Release workflow builds images once and pushes immutable ECR digests.
- Deploy workflow reads promotion metadata and environment config.
- Deploy workflow records the current task definition as rollback baseline.
- Deploy workflow registers a new task definition revision with digest image URIs.
- Deploy workflow updates ECS services, waits for stability, checks ALB target health, and runs HTTP health checks.
- Failed verification restores the previous task definition and writes rollback evidence.

EC2 SSH is optional:

- Deploy workflow selects hosts based on `single-node` or `distributed`.
- Each host pulls immutable ECR digest images.
- The current container image is recorded as rollback baseline.
- Containers are restarted over SSH.
- HTTP checks run per selected host.
- Failed verification restores the previous image digest when available.

## Workflow Order

1. `ci.yml`: runs service checks from `.cicd/project.yaml`.
2. `release.yml`: builds and pushes selected service images, then uploads `promotion-metadata.json`.
3. `deploy-aws.yml`: downloads promotion metadata, deploys ECS or EC2, verifies health, and rolls back on failed verification.

`ci.yml` explicitly installs `pyyaml` before parsing `.cicd/project.yaml`. Missing service commands are skipped only with a summary reason; an empty service set fails CI.

`release.yml` deploys image digests, not mutable tags. The metadata includes commit SHA, actor, run URL, release ID, selected services, image tags, and immutable digest URIs.

`deploy-aws.yml` requires the release workflow run ID so it can download the matching `promotion-metadata.json` artifact.

## Rollback Strategy

Automatic rollback covers:

- ECS service update followed by ALB target health failure.
- ECS service update followed by HTTP health failure.
- EC2 container restart followed by HTTP health failure.

Rollback evidence is written to `rollback-evidence.json`. Deployment evidence is written to `deployment-evidence.json`.

Human intervention is required for:

- destructive database migrations
- missing AWS permissions
- missing secrets
- broken network infrastructure
- rollback that cannot restore a healthy service

## Known Limits

- This project installs CI/CD into an existing application repository; it does not provision AWS infrastructure from scratch.
- EC2 SSH assumes target hosts can authenticate to ECR, typically through an instance role or installed AWS credentials.
- Database migrations are detected and documented, but application-specific migration scripts remain in the target repository.
- The skill must stop before replacing existing CI/CD files unless the user explicitly approves the overwrite.
