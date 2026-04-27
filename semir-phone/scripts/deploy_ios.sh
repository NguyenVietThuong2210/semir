#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_ios.sh  —  Build signed IPA and upload to TestFlight / App Store
#
# ⚠️  REQUIRES macOS with Xcode 15+ installed. Cannot run on Windows.
#
# Usage:
#   bash scripts/deploy_ios.sh          # upload to TestFlight (beta)
#   bash scripts/deploy_ios.sh release  # submit for App Store review
#
# Required env vars (copy .env.ios.template → .env.ios, fill in):
#   APPLE_ID           developer@yourcompany.com
#   ITC_TEAM_ID        App Store Connect team ID (numeric, e.g. 123456789)
#   APPLE_TEAM_ID      Apple Developer team ID (alphanumeric, e.g. ABCDE12345)
#   MATCH_GIT_URL      git@github.com:your-org/certs.git
#   MATCH_PASSWORD     Fastlane Match encryption password
#   API_BASE_URL       https://analytics-customer-dashboard.com/api/v1/
#   ENVIRONMENT        production
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

MODE="${1:-beta}"              # beta (TestFlight) | release (App Store)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── 0. Platform check ─────────────────────────────────────────────────────────
if [[ "$(uname)" != "Darwin" ]]; then
  echo "[deploy] ERROR: iOS builds require macOS. This script cannot run on $(uname)."
  exit 1
fi

# ── 1. Load secrets ───────────────────────────────────────────────────────────
ENV_FILE="$ROOT/.env.ios"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  echo "[deploy] Loaded secrets from .env.ios"
else
  echo "[deploy] ERROR: $ENV_FILE not found."
  echo "         Copy scripts/.env.ios.template → .env.ios and fill in your values."
  exit 1
fi

# ── 2. Validate required vars ─────────────────────────────────────────────────
for VAR in APPLE_ID ITC_TEAM_ID APPLE_TEAM_ID MATCH_GIT_URL MATCH_PASSWORD API_BASE_URL; do
  if [[ -z "${!VAR:-}" ]]; then
    echo "[deploy] ERROR: $VAR is not set in .env.ios"
    exit 1
  fi
done

# ── 3. Version bump ───────────────────────────────────────────────────────────
echo "[deploy] Current version:"
grep '^version:' "$ROOT/pubspec.yaml"

read -rp "[deploy] Bump build number? (y/N): " BUMP
if [[ "${BUMP,,}" == "y" ]]; then
  CURRENT=$(grep '^version:' "$ROOT/pubspec.yaml" | sed 's/version: //')
  BASE="${CURRENT%%+*}"
  BUILD="${CURRENT##*+}"
  NEW_BUILD=$((BUILD + 1))
  sed -i '' "s/^version: .*/version: $BASE+$NEW_BUILD/" "$ROOT/pubspec.yaml"
  echo "[deploy] Version updated → $BASE+$NEW_BUILD"
fi

# ── 4. Clean + get dependencies ───────────────────────────────────────────────
cd "$ROOT"
echo "[deploy] flutter clean && flutter pub get ..."
flutter clean
flutter pub get

# ── 5. Run tests ──────────────────────────────────────────────────────────────
echo "[deploy] Running widget tests ..."
flutter test test/widget/ --reporter compact

# ── 6. Sync signing certificates via Fastlane Match ──────────────────────────
echo "[deploy] Syncing certificates (fastlane match) ..."
export APPLE_ID ITC_TEAM_ID APPLE_TEAM_ID MATCH_GIT_URL MATCH_PASSWORD
bundle exec fastlane match appstore --readonly

# ── 7. Build IPA ──────────────────────────────────────────────────────────────
echo "[deploy] Building release IPA ..."
flutter build ipa \
  --dart-define=API_BASE_URL="$API_BASE_URL" \
  --dart-define=ENVIRONMENT="${ENVIRONMENT:-production}" \
  --obfuscate \
  --split-debug-info=build/debug-info/ios \
  --export-options-plist=ios/ExportOptions.plist

IPA_DIR="$ROOT/build/ios/ipa"
echo "[deploy] IPA ready in: $IPA_DIR"

# ── 8. Upload ─────────────────────────────────────────────────────────────────
if [[ "$MODE" == "release" ]]; then
  echo "[deploy] Uploading to App Store for review ..."
  bundle exec fastlane ios release
else
  echo "[deploy] Uploading to TestFlight ..."
  bundle exec fastlane ios beta
fi

echo ""
echo "✓ iOS deployment complete!"
echo "  Mode       : $MODE"
echo "  Next step  : Open App Store Connect → TestFlight to monitor processing"
echo "               (usually ready within 5-15 minutes)"
