#!/usr/bin/env bash
# One-time frontend setup. Requires Node 20+.
# Run from mini_obd_build/ or mini_obd_build/app/web/
set -e

cd "$(dirname "${BASH_SOURCE[0]}")"

echo "==> Installing npm dependencies..."
npm install

echo ""
echo "Done. Commands:"
echo "  npm run dev    — start dev server at http://localhost:3000"
echo "  npm run build  — build static export to app/web/out/"
echo ""
echo "Then deploy to Pi:"
echo "  bash app/deploy.sh    (from project root)"
