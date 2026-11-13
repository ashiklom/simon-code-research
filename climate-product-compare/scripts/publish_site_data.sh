#!/usr/bin/env bash
# Publish site/public/data to the assets repo and pin the site to that commit.
# Usage: scripts/publish_site_data.sh /path/to/simon-code-research-assets-clone
set -euo pipefail
ASSETS=${1:?path to a clone of ashiklom/simon-code-research-assets}
HERE=$(cd "$(dirname "$0")/.." && pwd)
DEST="$ASSETS/climate-product-compare/data"
rm -rf "$DEST" && mkdir -p "$(dirname "$DEST")" && cp -a "$HERE/site/public/data" "$DEST"
cd "$ASSETS"
git add -A climate-product-compare
# commit in batches of sites so each push stays moderate in size
mapfile -t SITES < <(ls climate-product-compare/data/site | sort)
git commit -q -m "climate-product-compare: site data (metadata)" -- climate-product-compare/README.md climate-product-compare/data/*.json || true
for ((i = 0; i < ${#SITES[@]}; i += 75)); do
  batch=("${SITES[@]:i:75}")
  git commit -q -m "climate-product-compare: site data (sites $((i + 1))-$((i + ${#batch[@]})))" \
    -- "${batch[@]/#/climate-product-compare/data/site/}" || true
  git -c push.negotiate=true push -q origin HEAD
done
git commit -q -am "climate-product-compare: site data (removals)" || true
git -c push.negotiate=true push -q origin HEAD
SHA=$(git rev-parse HEAD)
sed -i "s|simon-code-research-assets/[0-9a-f]\{40\}/|simon-code-research-assets/$SHA/|" "$HERE/site/.env.production"
echo "pinned site data to $SHA (site/.env.production); commit that change in simon-code-research"
