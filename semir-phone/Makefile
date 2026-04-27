# SemirPhone — development commands
# Run all commands from the semir-phone/ directory

.PHONY: run-ios run-android test snapshot build-ios build-android clean

# ── Development ──────────────────────────────────────────────────────────────

run-ios:
	flutter run -d "iPhone 15 Pro" \
		--dart-define=API_BASE_URL=http://localhost:8000/api/v1 \
		--dart-define=ENVIRONMENT=debug

run-android:
	flutter run -d "Pixel 7" \
		--dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1 \
		--dart-define=ENVIRONMENT=debug

# ── Testing ──────────────────────────────────────────────────────────────────

test:
	flutter test

# ── Visual Snapshots (QA gate: must open render/*.png and visually approve) ──

snapshot:
	flutter test --update-goldens test/golden/
	@echo ""
	@echo "Snapshots written to render/. Open each PNG and verify before marking any UI task done."
	@echo "QA checklist: render/README.md"

# ── Release Builds ───────────────────────────────────────────────────────────

build-ios:
	@echo "Building signed IPA via Fastlane..."
	fastlane ios beta

build-android:
	@echo "Building signed AAB via Fastlane..."
	fastlane android beta

# ── Utility ──────────────────────────────────────────────────────────────────

clean:
	flutter clean
	flutter pub get
