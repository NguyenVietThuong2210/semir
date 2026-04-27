# Deployment

Deployment is split into two separate guides:

| Platform | File |
|----------|------|
| **Google Play (Android)** | [DEPLOY_ANDROID.md](DEPLOY_ANDROID.md) |
| **App Store (iOS)** | [DEPLOY_IOS.md](DEPLOY_IOS.md) |

Each guide covers the full path: machine setup → signing → local testing → production release.

---

## Quick reference

| Task | Command |
|------|---------|
| Run on Android emulator (debug) | `flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1 --dart-define=ENVIRONMENT=debug` |
| Run on iOS simulator (debug) | `flutter run --dart-define=API_BASE_URL=http://localhost:8000/api/v1 --dart-define=ENVIRONMENT=debug` |
| Run all widget tests | `flutter test test/widget/` |
| Deploy to Google Play Internal | `bash scripts/deploy_android.sh` |
| Deploy to TestFlight | `bash scripts/deploy_ios.sh` |
| Deploy to App Store review | `bash scripts/deploy_ios.sh release` |
