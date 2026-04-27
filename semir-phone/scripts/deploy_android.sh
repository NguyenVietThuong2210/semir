#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_android.sh  —  Build signed AAB and upload to Google Play
#
# Usage:
#   bash scripts/deploy_android.sh            # upload to Internal Testing
#   bash scripts/deploy_android.sh production # upload to Production track
#
# Required env vars (copy .env.android.template → .env.android, fill in):
#   KEYSTORE_PATH      absolute path to semir.jks
#   KEYSTORE_PASS      keystore password
#   KEY_ALIAS          alias used when creating the keystore (semirphone)
#   KEY_PASS           key password
#   PLAY_STORE_JSON_KEY  contents of the service-account JSON (single line)
#   API_BASE_URL       https://analytics-customer-dashboard.com/api/v1/
#   ENVIRONMENT        production
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

TRACK="${1:-internal}"         # internal | alpha | beta | production
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── 0. Load secrets ──────────────────────────────────────────────────────────
ENV_FILE="$ROOT/.env.android"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
  echo "[deploy] Loaded secrets from .env.android"
else
  echo "[deploy] ERROR: $ENV_FILE not found."
  echo "         Copy scripts/.env.android.template → .env.android and fill in your values."
  exit 1
fi

# ── 1. Validate required vars ─────────────────────────────────────────────────
for VAR in KEYSTORE_PATH KEYSTORE_PASS KEY_ALIAS KEY_PASS PLAY_STORE_JSON_KEY API_BASE_URL; do
  if [[ -z "${!VAR:-}" ]]; then
    echo "[deploy] ERROR: $VAR is not set in .env.android"
    exit 1
  fi
done

if [[ ! -f "$KEYSTORE_PATH" ]]; then
  echo "[deploy] ERROR: keystore not found at $KEYSTORE_PATH"
  echo "         Run this once to create it:"
  echo "           keytool -genkey -v -keystore semir.jks -alias semirphone -keyalg RSA -keysize 2048 -validity 10000"
  exit 1
fi

# ── 2. Version bump ───────────────────────────────────────────────────────────
echo "[deploy] Current version:"
grep '^version:' "$ROOT/pubspec.yaml"

read -rp "[deploy] Bump build number? (y/N): " BUMP
if [[ "${BUMP,,}" == "y" ]]; then
  CURRENT=$(grep '^version:' "$ROOT/pubspec.yaml" | sed 's/version: //')
  BASE="${CURRENT%%+*}"
  BUILD="${CURRENT##*+}"
  NEW_BUILD=$((BUILD + 1))
  sed -i "s/^version: .*/version: $BASE+$NEW_BUILD/" "$ROOT/pubspec.yaml"
  echo "[deploy] Version updated → $BASE+$NEW_BUILD"
fi

# ── 3. Clean + get dependencies ───────────────────────────────────────────────
cd "$ROOT"
echo "[deploy] flutter clean && flutter pub get ..."
flutter clean
flutter pub get

# ── 4. Run tests ──────────────────────────────────────────────────────────────
echo "[deploy] Running widget tests ..."
flutter test test/widget/ --reporter compact

# ── 5. Build AAB (Android App Bundle) ────────────────────────────────────────
echo "[deploy] Building release AAB ..."
flutter build appbundle \
  --dart-define=API_BASE_URL="$API_BASE_URL" \
  --dart-define=ENVIRONMENT="${ENVIRONMENT:-production}" \
  --obfuscate \
  --split-debug-info=build/debug-info/android

AAB="$ROOT/build/app/outputs/bundle/release/app-release.aab"
if [[ ! -f "$AAB" ]]; then
  echo "[deploy] ERROR: AAB not found at $AAB — build failed."
  exit 1
fi
echo "[deploy] AAB ready: $AAB"

# ── 6. Upload to Google Play ──────────────────────────────────────────────────
echo "[deploy] Uploading to Play Store track: $TRACK ..."
export KEYSTORE_PATH KEYSTORE_PASS KEY_ALIAS KEY_PASS PLAY_STORE_JSON_KEY
bundle exec fastlane android beta track:"$TRACK"

echo ""
echo "✓ Android deployment complete!"
echo "  Track      : $TRACK"
echo "  AAB        : $AAB"
echo "  Next step  : Open Google Play Console → Internal Testing → Promote"
