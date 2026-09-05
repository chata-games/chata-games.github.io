#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
site_dir=${1:-"$repo_root/dist/pages"}
marker=.chata-games-pages-staging

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "Missing required build output: $1" >&2
    exit 1
  fi
}

require_file "$repo_root/forest-rescue/dist/app/index.html"
require_file "$repo_root/trolluv-sklep/dist/index.html"

mkdir -p "$(dirname "$site_dir")"
site_parent=$(cd "$(dirname "$site_dir")" && pwd)
site_dir="$site_parent/$(basename "$site_dir")"
if [[ "$repo_root" == "$site_dir" || "$repo_root" == "$site_dir/"* ]]; then
  echo "Refusing to replace unsafe staging path: $site_dir" >&2
  exit 1
fi
if [[ -d "$site_dir" ]] && [[ -n "$(find "$site_dir" -mindepth 1 -maxdepth 1 -print -quit)" ]] && [[ ! -f "$site_dir/$marker" ]]; then
  echo "Refusing to replace unmarked nonempty directory: $site_dir" >&2
  exit 1
fi

staging_dir=$(mktemp -d "$site_parent/.pages-stage.XXXXXX")
trap 'rm -rf -- "$staging_dir"' EXIT
touch "$staging_dir/$marker"

cp "$repo_root/index.html" "$repo_root/.nojekyll" "$staging_dir/"
cp -R "$repo_root/assets" "$staging_dir/assets"

mkdir -p "$staging_dir/forest-rescue" "$staging_dir/trolluv-sklep"
cp -R "$repo_root/forest-rescue/dist/app/." "$staging_dir/forest-rescue/"
cp -R "$repo_root/trolluv-sklep/dist/." "$staging_dir/trolluv-sklep/"

for game in daligame grunts-way-home tvojekariera unikovka; do
  require_file "$repo_root/$game/index.html"
  mkdir -p "$staging_dir/$game"
  rsync -a \
    --exclude='.git' \
    --exclude='.github' \
    --exclude='.claude' \
    --exclude='node_modules' \
    --exclude='tools' \
    --exclude='tests' \
    "$repo_root/$game/" "$staging_dir/$game/"
done

if [[ -d "$site_dir" ]]; then
  rm -rf -- "$site_dir"
fi
mv "$staging_dir" "$site_dir"
trap - EXIT
echo "Staged GitHub Pages site at $site_dir"
