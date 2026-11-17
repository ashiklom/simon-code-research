#!/usr/bin/env bash
# Publish site/public/data to the assets repo and pin the site to that commit.
# Vendored from climate-product-compare/scripts/publish_site_data.sh (folder name, batch size,
# and a README for the assets folder changed).
# Usage: scripts/publish_site_data.sh /path/to/simon-code-research-assets-clone
# The clone may be sparse (git sparse-checkout set air-quality-data-comparison).
set -euo pipefail
ASSETS=${1:?path to a clone of ashiklom/simon-code-research-assets}
HERE=$(cd "$(dirname "$0")/.." && pwd)
NAME=air-quality-data-comparison
DEST="$ASSETS/$NAME/data"
rm -rf "$DEST" && mkdir -p "$(dirname "$DEST")" && cp -a "$HERE/site/public/data" "$DEST"
cat > "$ASSETS/$NAME/README.md" <<'EOF'
# air-quality-data-comparison site data

Per-site Parquet and metrics JSON for the
[air-quality-data-comparison](https://github.com/ashiklom/simon-code-research/tree/main/air-quality-data-comparison)
website (https://ashiklom.github.io/simon-code-research/air-quality-data-comparison/).

- Produced by `mise run sitedata` in that experiment (`site/public/data`), copied here by
  `scripts/publish_site_data.sh`.
- Read by the browser (`site/src/main.js`) from `raw.githubusercontent.com` at the commit pinned in
  the experiment's `site/.env.production` (`VITE_DATA_BASE`).
- Layout: `data/{sites,products,summary,scales}.json`; `data/site/<id>/{daily,monthly}.parquet`,
  `hourly/2023.parquet`, `metrics.json`.
EOF
cd "$ASSETS"
git add -A --sparse "$NAME"
# commit in batches of sites so each push stays moderate in size (~10 MB)
mapfile -t SITES < <(ls "$NAME/data/site" | sort)
git commit -q -m "$NAME: site data (metadata)" -- "$NAME/README.md" "$NAME"/data/*.json || true
git -c push.negotiate=true push -q origin HEAD:main
for ((i = 0; i < ${#SITES[@]}; i += 150)); do
  batch=("${SITES[@]:i:150}")
  git commit -q -m "$NAME: site data (sites $((i + 1))-$((i + ${#batch[@]})))" \
    -- "${batch[@]/#/$NAME/data/site/}" || true
  for attempt in 1 2 3 4; do
    git -c push.negotiate=true push -q origin HEAD:main && break
    sleep $((5 * 2 ** attempt))
  done
done
git commit -q -m "$NAME: site data (removals)" -- "$NAME" || true
git -c push.negotiate=true push -q origin HEAD:main
SHA=$(git rev-parse HEAD)
sed -i "s|simon-code-research-assets/[0-9a-f]\{40\}/|simon-code-research-assets/$SHA/|" "$HERE/site/.env.production"
echo "pinned site data to $SHA (site/.env.production); commit that change in simon-code-research"
