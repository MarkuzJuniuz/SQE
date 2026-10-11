#!/bin/sh
# Release helper (Ops O). usage: tools/mkzip.sh <version>  ->  release/SQE_v<version>.zip
# Zips the tracked tree WITHOUT the GitHub-facing files, so a select-all paste over a checkout never touches them.
# Run from the repo root on the tagged commit. For the Windows build the Actions workflow (release.yml) is the real release path.
set -e
v="${1:?usage: tools/mkzip.sh <version>}"
root="$(git rev-parse --show-toplevel)"
out="$root/release"; tmp="$(mktemp -d)"
mkdir -p "$out" "$tmp/SQE"
git -C "$root" archive HEAD | tar -x -C "$tmp/SQE"
( cd "$tmp/SQE" && rm -rf .github .gitignore README.md LICENSE SQE.spec CLAUDE.md docs/images docs/GITHUB_GUIDE.md )
( cd "$tmp" && zip -qr "$out/SQE_v$v.zip" SQE )
rm -rf "$tmp"
echo "wrote $out/SQE_v$v.zip"
