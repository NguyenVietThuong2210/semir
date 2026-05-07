# iOS — Deploy lên iPhone

> ⚠️ **Bắt buộc phải có Mac với macOS 13+. Không thể build iOS trên Windows.**

---

## Part 1: Cài đặt môi trường (Mac mới — làm 1 lần)

### 1.1 Cài Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Apple Silicon (M1/M2/M3) — chạy thêm:
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"

brew --version   # kiểm tra OK
```

### 1.2 Cài Xcode

1. App Store → tìm **Xcode** → Install (~15 GB, 30–60 phút)
2. Mở Xcode lần đầu → chờ cài thêm components → đóng lại
3. Chạy:
   ```bash
   sudo xcodebuild -license accept
   xcode-select --install
   ```

### 1.3 Cài Flutter + CocoaPods

```bash
brew install --cask flutter
sudo gem install cocoapods

flutter --version   # kiểm tra OK
pod --version       # kiểm tra OK
```

### 1.4 Kiểm tra toàn bộ

```bash
flutter doctor
```

Cần thấy ✓ ở: Flutter, Xcode, CocoaPods.

---

## Part 2: Lấy code và cấu hình (làm 1 lần)

### 2.1 Clone và cài dependencies

```bash
mkdir -p ~/Projects && cd ~/Projects
git clone <repo-url> semir
cd semir/semir-phone
flutter pub get
```

### 2.2 Tạo iOS platform files

```bash
cd ~/Projects/semir/semir-phone
flutter create --platforms=ios .
cd ios && pod install && cd ..
```

> `pod install` lần đầu mất 5–10 phút.

### 2.3 Cấu hình tên app

Mở `ios/Runner/Info.plist`, thêm vào trong `<dict>`:

```xml
<key>CFBundleDisplayName</key>
<string>SB Dashboard</string>
<key>CFBundleName</key>
<string>SBDashboard</string>
```

> `CFBundleDisplayName` = tên hiển thị trên màn hình iPhone.
> `CFBundleName` = tên kỹ thuật (không có space hoặc ký tự đặc biệt).

### 2.4 Cấu hình Bundle ID và Signing trong Xcode

```bash
open ios/Runner.xcworkspace
```

- Click **Runner** ở sidebar → tab **Signing & Capabilities**
- Tick **Automatically manage signing**
- **Team**: chọn Apple ID của bạn (thêm qua Xcode → Settings → Accounts → + nếu chưa có)
- **Bundle Identifier**: `com.semir.semirphone`
- Tab **General** → **Version**: `1.0.0`, **Build**: `1`
- **⌘S** → đóng Xcode

> **Lưu ý:** Apple ID trên Mac (developer account) và Apple ID trên iPhone (personal account) khác nhau là bình thường — không ảnh hưởng gì.

---

## Part 3: Fix lỗi Signing (làm 1 lần nếu gặp errSecInternalComponent)

Lỗi `errSecInternalComponent` xảy ra khi private key trong Keychain không cho phép tool `codesign` truy cập tự động.

### Bước 1 — Tạo certificate mới trong Xcode

Xcode → Settings → Accounts → chọn Apple ID → **Manage Certificates** → **+** → **Apple Development**

### Bước 2 — Set partition list cho keychain

```bash
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "MẬT_KHẨU_MAC" ~/Library/Keychains/login.keychain-db
```

> Thay `MẬT_KHẨU_MAC` bằng mật khẩu login Mac. Lệnh này cho phép `codesign` truy cập key không cần prompt trong quá trình build.

### Bước 3 — Unlock keychain trước khi build

```bash
security unlock-keychain -p "MẬT_KHẨU_MAC" ~/Library/Keychains/login.keychain-db
```

### Kiểm tra certificate hợp lệ

```bash
security find-identity -v -p codesigning
# Phải thấy: 1 valid identities found
# Ví dụ: "Apple Development: your@email.com (TEAMID)"
```

### Nếu vẫn lỗi — Reset keychain

1. Keychain Access → Settings → **Reset My Default Keychain** → nhập Mac password
2. Xcode → Settings → Accounts → Manage Certificates → **+** → Apple Development (tạo lại certificate)
3. Chạy lại Bước 2 và 3

---

## Part 4: Build Release và cài lên iPhone (flow chính)

### 4.1 Bật Developer Mode trên iPhone (làm 1 lần)

iPhone → **Cài đặt** → **Quyền riêng tư & Bảo mật** → **Chế độ dành cho nhà phát triển** → Bật → Khởi động lại → Xác nhận

### 4.2 Build release

```bash
cd ~/Projects/semir/semir-phone

# Unlock keychain trước
security unlock-keychain -p "MẬT_KHẨU_MAC" ~/Library/Keychains/login.keychain-db

# Build
flutter build ios --release \
  --dart-define=API_BASE_URL=https://analytics-customer-dashboard.com/api/v1 \
  --dart-define=ENVIRONMENT=production
```

> Build mất khoảng 2–5 phút. File output: `build/ios/iphoneos/Runner.app`

### 4.3 Cài lên iPhone qua Xcode

1. Cắm cáp iPhone vào Mac
2. Mở Xcode → menu **Window → Devices and Simulators** (`Shift+Cmd+2`)
3. Chọn iPhone ở panel trái
4. Phần **Installed Apps** → nhấn **`+`**
5. Chọn file: `semir-phone/build/ios/iphoneos/Runner.app` → **Open**
6. Chờ install xong → **rút cáp**

App sẽ xuất hiện trên màn hình iPhone và chạy bình thường không cần cáp.

### 4.4 Trust Developer Certificate (lần đầu)

Nếu iPhone hiện thông báo "Untrusted Developer":

iPhone → **Cài đặt** → **Cài đặt chung** → **VPN & Quản lý thiết bị** → chọn Apple ID → **Tin tưởng**

---

## Part 5: Wireless Debugging (debug không cần cáp)

Nếu muốn chạy debug mode mà không cần cáp (cần cùng mạng WiFi):

1. Cắm cáp → chạy `flutter run` lần đầu
2. Xcode → Window → Devices and Simulators → chọn iPhone → tick **Connect via network**
3. Rút cáp → `flutter run` tiếp theo sẽ kết nối qua WiFi

> Wireless chỉ dùng cho debug. Release build không cần bước này.

---

## Part 6: Tăng version và rebuild

Trước mỗi lần build mới, tăng build number trong `pubspec.yaml`:

```yaml
version: 1.0.0+1   # lần đầu
version: 1.0.0+2   # lần 2
version: 1.0.1+3   # bug fix
```

Sau đó sync vào Xcode: Runner → General → Version và Build phải khớp.

Build lại từ Bước 4.2.

---

## Part 7: Đẩy lên App Store (khi sẵn sàng)

### 7.1 Đăng ký Apple Developer Program ($99/năm)

https://developer.apple.com → Enroll → Individual → Thanh toán → Chờ 1–2 ngày

### 7.2 Tạo App ID

developer.apple.com → Certificates, Identifiers & Profiles → Identifiers → + → App IDs:
- Bundle ID: `com.semir.semirphone`

### 7.3 Tạo app trên App Store Connect

appstoreconnect.apple.com → My Apps → + → New App:
- Name: **SB Dashboard**
- Bundle ID: `com.semir.semirphone`

### 7.4 Build IPA và upload

```bash
security unlock-keychain -p "MẬT_KHẨU_MAC" ~/Library/Keychains/login.keychain-db

flutter build ipa \
  --dart-define=API_BASE_URL=https://analytics-customer-dashboard.com/api/v1 \
  --dart-define=ENVIRONMENT=production
```

Upload IPA lên App Store Connect:

```bash
xcrun altool --upload-app \
  --type ios \
  --file build/ios/ipa/semir_phone.ipa \
  --username "apple_id@email.com" \
  --password "@keychain:AC_PASSWORD"
```

Hoặc mở `build/ios/ipa/` → kéo file `.ipa` vào **Transporter** app (tải từ App Store).

### 7.5 TestFlight → App Store

1. App Store Connect → SB Dashboard → TestFlight → thêm testers
2. Sau khi test OK: App Store → + Version → chọn build → Submit for Review
3. Apple review: 24–48 giờ

---

## Checklist mỗi lần release

- [ ] `flutter test` pass toàn bộ 226 tests
- [ ] Version tăng trong `pubspec.yaml` và khớp Xcode
- [ ] `security unlock-keychain` chạy trước build
- [ ] `API_BASE_URL` trỏ đúng production
- [ ] Test trên iPhone thật trước khi submit

---

## Lỗi thường gặp

| Lỗi | Cách sửa |
|-----|----------|
| `errSecInternalComponent` | Chạy `security set-key-partition-list` (Part 3) |
| `The specified item is no longer valid` | Stale keychain entry — bỏ qua, không ảnh hưởng build |
| `ptrace: Operation not permitted` | Bật Developer Mode trên iPhone (Part 4.1) |
| `Untrusted Developer` trên iPhone | Settings → VPN & Device Management → Trust (Part 4.4) |
| `pod install` fails | `cd ios && pod repo update && pod install` |
| `No profiles for com.semir.semirphone` | Xcode → Signing & Capabilities → fix signing → build lại |
| `flutter: command not found` | Mở terminal mới hoặc `source ~/.zshrc` |
| `CocoaPods not installed` | `sudo gem install cocoapods` |
| Build number đã tồn tại (App Store) | Tăng build number trong `pubspec.yaml` rồi build lại |
