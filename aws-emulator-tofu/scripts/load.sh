#!/usr/bin/env bash
# Load vectors into the deployed Aurora cluster through the RDS Data API.
set -euo pipefail
cd "$(dirname "$0")/.."
eval "$(scripts/emulator.sh env)"
export DB_CLUSTER_ARN="$(tofu -chdir=infra output -raw db_cluster_arn)"
export DB_SECRET_ARN="$(tofu -chdir=infra output -raw db_secret_arn)"
pixi run python scripts/load_vectors.py
