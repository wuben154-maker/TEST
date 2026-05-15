# Database Migration Guidance

Database migration is an application concern, not a hard-coded workflow in this repository. The `aws-cicd` skill detects migration tooling and records it in `.cicd/project.yaml`; target repositories keep their framework-specific migration scripts.

## Detection

Detect common migration systems before installing workflows:

- Prisma
- Drizzle
- Flyway
- Liquibase
- Django migrations
- Alembic
- Rails migrations
- Knex or TypeORM migrations

If migration tooling is detected, report the migration command and whether the backend deploy should be blocked until migration prechecks pass.

## Strategy

Use Expand -> Migrate -> Contract:

1. Expand: add backward-compatible schema changes first.
2. Migrate: deploy code that can read and write both old and new schema, then run backfills.
3. Contract: remove legacy schema only after the verification window passes.

## Pipeline Order

For backend services with database migrations:

1. Precheck database connectivity, credentials, migration lock, and backup freshness.
2. Run migration plan or dry-run.
3. Apply the approved migration package.
4. Verify schema version and a key read/write smoke query.
5. Deploy the backend service.

If migration fails, stop the backend deploy. Do not assume database rollback is safe.

## Irreversible Changes

Require explicit human approval for:

- destructive data drops
- one-way transforms without backup
- incompatible type conversions without fallback
- large backfills that can lock hot tables

Automatic CI/CD rollback can restore application containers, but it cannot safely undo destructive data changes. Treat destructive migration rollback as a manual incident path.
