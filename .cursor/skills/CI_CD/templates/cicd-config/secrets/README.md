# CI/CD Secret Boundary

Do not commit real secret values to `.cicd/`.

The generated environment files may store secret names, variable names, and ARN references only. Real values belong in GitHub Secrets, GitHub Variables, AWS Secrets Manager, or AWS Systems Manager Parameter Store.

## GitHub Secrets

- `AWS_RELEASE_ROLE_ARN`: IAM role ARN trusted by GitHub OIDC for release and deploy workflows.
- `AWS_EC2_SSH_PRIVATE_KEY`: private key for EC2 SSH deployment, required only when `deployment.target` is `ec2-ssh`.

## GitHub Variables

Define only the variables needed by enabled services:

- `AWS_REGION`
- `ECR_REPOSITORY_FRONTEND`
- `ECR_REPOSITORY_BACKEND`
- `ECR_REPOSITORY_WORKER`

## AWS Secret Stores

Application runtime values should live in AWS Secrets Manager or SSM Parameter Store:

- database credentials
- application runtime secrets
- third-party API keys
- OAuth credentials

Reference these values by name or ARN in `.cicd/env/<environment>.yaml`.
