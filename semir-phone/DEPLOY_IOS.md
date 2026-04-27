# iOS — App Store

> ⚠️ **Yêu cầu Mac với macOS 13+ và Xcode 15+. Không thể build iOS trên Windows.**

---

## Part 1: Chạy local → Simulator → Thiết bị thật

### 1.1 Cài đặt môi trường (làm 1 lần)

**Xcode**
1. Mở App Store trên Mac → tìm "Xcode" → Install (khoảng 15 GB, mất 30–60 phút)
2. Chấp nhận license:
   ```bash
   sudo xcodebuild -license accept
   ```
3. Cài command-line tools:
   ```bash
   xcode-select --install
   ```

**Flutter SDK**
```bash
# Cài qua Homebrew (khuyến nghị)
brew install --cask flutter

# Kiểm tra — mục "Xcode" phải có ✓
flutter doctor
```

**CocoaPods** (quản lý dependency iOS)
```bash
sudo gem install cocoapods
pod --version   # in ra số version là OK
```

**Ruby + Bundler** (dùng cho Fastlane ở Part 2)
```bash
brew install rbenv ruby-build
rbenv install 3.2.0
rbenv global 3.2.0

# Mở terminal mới, rồi:
gem install bundler
```

---

### 1.2 Tạo platform files iOS (làm 1 lần)

Thư mục `ios/` chưa tồn tại. Chạy lệnh này từ thư mục dự án:

```bash
cd /path/to/semir-phone
flutter create --platforms=ios .
```

Lệnh này tạo ra `ios/` với Xcode project. Code trong `lib/` không bị ảnh hưởng.

Cài dependencies iOS:
```bash
cd ios && pod install && cd ..
```

---

### 1.3 Cấu hình tên app và bundle ID

**Tên hiển thị** — Mở `ios/Runner/Info.plist`, thêm 2 key sau vào trong `<dict>` gốc:
```xml
<key>CFBundleDisplayName</key>
<string>S&amp;B Dashboard</string>
<key>CFBundleName</key>
<string>SandBDashboard</string>
```

**Bundle ID** — Mở Xcode:
```bash
open ios/Runner.xcworkspace
```
Trong Xcode:
1. Click **Runner** ở sidebar trái
2. Chọn target **Runner** → tab General
3. Bundle Identifier: `com.semir.semirphone`
4. Version: `1.0.0`, Build: `1` (phải khớp `pubspec.yaml`)

---

### 1.4 Chạy trên iOS Simulator

1. Mở Simulator:
   ```bash
   open -a Simulator
   ```
2. Kiểm tra simulator đã chạy:
   ```bash
   flutter devices
   # Phải thấy: "iPhone 15 Pro (simulator)"
   ```
3. Chạy app:
   ```bash
   cd /path/to/semir-phone
   flutter run --dart-define=API_BASE_URL=http://localhost:8000/api/v1 --dart-define=ENVIRONMENT=debug
   ```
   > `localhost` kết nối thẳng đến backend đang chạy trên máy Mac.

Hot reload: bấm `r` trong terminal để reload ngay mà không cần restart app.

---

### 1.5 Chạy trên thiết bị iPhone thật

**Bước 1 — Thêm Apple ID vào Xcode:**
- Xcode → Settings → Accounts → `+` → Apple ID → đăng nhập

**Bước 2 — Cắm iPhone qua USB:**
- iPhone hiện thông báo "Trust This Computer?" → bấm **Trust**
- Kiểm tra:
  ```bash
  flutter devices
  # Phải thấy tên iPhone trong danh sách
  ```

**Bước 3 — Cấu hình signing trong Xcode:**
- Runner → Signing & Capabilities → chọn **Team** (Apple ID của bạn)
- Xcode sẽ tự tạo provisioning profile cho development

**Bước 4 — Tìm IP của Mac (để app kết nối đến backend):**
```bash
ifconfig | grep "inet 192"
# Ghi lại địa chỉ IPv4, ví dụ: 192.168.1.10
```

**Bước 5 — Chạy:**
```bash
flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8000/api/v1 --dart-define=ENVIRONMENT=debug
```
> iPhone và Mac phải cùng mạng WiFi.

Lần đầu chạy trên iPhone: vào Settings → General → VPN & Device Management → trust developer certificate.

---

### 1.6 Build IPA debug để chia sẻ kiểm thử (không qua App Store)

```bash
flutter build ios --debug \
  --dart-define=API_BASE_URL=https://analytics-customer-dashboard.com/api/v1/ \
  --dart-define=ENVIRONMENT=debug
```

Cài trực tiếp qua Xcode: Devices and Simulators → chọn iPhone → `+` → chọn file `.app` trong `build/ios/`.

---

### 1.7 Chạy tests

```bash
# Chạy toàn bộ widget tests (không cần thiết bị)
flutter test test/widget/

# Chạy một test cụ thể
flutter test test/widget/login_page_test.dart
```

---

## Part 2: Build release → Đẩy lên App Store

### 2.1 Tạo Apple Developer account (làm 1 lần)

1. Truy cập https://developer.apple.com → **Enroll** vào Apple Developer Program
2. Chi phí: **$99/năm** (bắt buộc để publish lên App Store)
3. Quá trình duyệt mất 1–2 ngày làm việc

---

### 2.2 Tạo App ID và app trên App Store Connect (làm 1 lần)

**App ID (bundle identifier):**
1. https://developer.apple.com → Certificates, Identifiers & Profiles → Identifiers → `+`
2. Chọn App IDs → App
3. Bundle ID: `com.semir.semirphone` (explicit, không dùng wildcard)

**App trên App Store Connect:**
1. https://appstoreconnect.apple.com → My Apps → `+` → New App
2. Platform: iOS
3. Name: **S&B Dashboard**
4. Bundle ID: `com.semir.semirphone`
5. SKU: `semirphone`
6. Hoàn thành store listing, content rating, pricing

---

### 2.3 Cài đặt Fastlane (làm 1 lần)

```bash
cd /path/to/semir-phone
bundle install
```

Nếu chưa có `Gemfile`:
```ruby
# Gemfile
source "https://rubygems.org"
gem "fastlane"
```
Rồi chạy `bundle install` lại.

---

### 2.4 Tạo certificates với Fastlane Match (làm 1 lần)

Match lưu certificate vào private git repo để cả team dùng chung.

**Tạo private repo chứa certificates:**
1. GitHub → New repository → đặt tên `semir-certs` → **Private** → Create

**Khởi tạo Match:**
```bash
cd /path/to/semir-phone
bundle exec fastlane match init
# Chọn: git
# Nhập SSH URL của repo semir-certs: git@github.com:your-org/semir-certs.git
```

**Tạo App Store certificate:**
```bash
bundle exec fastlane match appstore
# Nhập password mạnh khi được hỏi → lưu password này vào password manager (MATCH_PASSWORD)
```

---

### 2.5 Tạo ExportOptions.plist (làm 1 lần)

Tạo file `ios/ExportOptions.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store</string>
    <key>teamID</key>
    <string>YOUR_APPLE_TEAM_ID</string>
    <key>uploadBitcode</key>
    <false/>
    <key>uploadSymbols</key>
    <true/>
    <key>compileBitcode</key>
    <false/>
</dict>
</plist>
```

Tìm Team ID tại: https://developer.apple.com → Account → Membership → Team ID (chuỗi chữ số + chữ cái).

---

### 2.6 Cấu hình secrets (làm 1 lần)

```bash
cp scripts/.env.ios.template .env.ios
nano .env.ios   # điền tất cả các giá trị
```

| Biến | Lấy ở đâu |
|------|-----------|
| `APPLE_ID` | Email Apple ID của bạn |
| `ITC_TEAM_ID` | App Store Connect → Users → account → cuộn xuống → Team ID (số) |
| `APPLE_TEAM_ID` | developer.apple.com → Account → Membership → Team ID (chữ + số) |
| `MATCH_GIT_URL` | SSH URL của repo `semir-certs` (bước 2.4) |
| `MATCH_PASSWORD` | Password bạn đặt trong bước 2.4 |
| `API_BASE_URL` | `https://analytics-customer-dashboard.com/api/v1/` |

---

### 2.7 Tăng version trước mỗi lần release

Mở `pubspec.yaml`, tăng build number:
```yaml
version: 1.0.0+1   # lần đầu
version: 1.0.0+2   # lần 2 (bắt buộc phải tăng, dù code không đổi)
version: 1.0.1+3   # bug fix
version: 1.1.0+4   # tính năng mới
```

Đồng bộ version vào Xcode: Runner → General → Version + Build phải khớp.

---

### 2.8 Build IPA và upload lên TestFlight

```bash
# Chạy từ thư mục semir-phone
bash scripts/deploy_ios.sh

# Upload thẳng lên App Store review (bỏ qua TestFlight):
bash scripts/deploy_ios.sh release
```

Script tự động:
1. Kiểm tra đang chạy trên Mac
2. Load secrets từ `.env.ios`
3. Hỏi có muốn tăng build number không
4. `flutter clean && flutter pub get`
5. Chạy toàn bộ widget tests (dừng nếu có test fail)
6. Sync certificates qua Fastlane Match
7. Build signed IPA (`flutter build ipa`)
8. Upload lên TestFlight

---

### 2.9 TestFlight testing

1. App Store Connect → S&B Dashboard → TestFlight
2. Thêm internal testers (Apple ID của team)
3. Họ nhận email → cài TestFlight app → cài S&B Dashboard
4. Build processing thường mất 5–15 phút sau khi upload

**Checklist test TestFlight:**
- [ ] App khởi động không crash
- [ ] Đăng nhập → hiển thị đúng username
- [ ] Trang Sales load dữ liệu trong 4 giây (WiFi)
- [ ] Customer Lookup: tìm theo phone → hiện số đã mask
- [ ] Store Detail: chọn store → đủ 3 section load
- [ ] Đăng xuất → quay về màn login
- [ ] Kill app → mở lại → vẫn còn đăng nhập (session persist)
- [ ] Không có crash trong App Store Connect → TestFlight → Crashes

---

### 2.10 Submit lên App Store

Sau khi TestFlight pass:
```bash
bash scripts/deploy_ios.sh release
```

Trong App Store Connect:
1. S&B Dashboard → App Store → `+` Version
2. Chọn build từ TestFlight
3. Viết release notes (tiếng Anh)
4. Thêm screenshots (bắt buộc: 6.5" iPhone, 5.5" iPhone)
5. Submit for Review

Apple review thường mất **24–48 giờ**.

---

### Checklist mỗi lần release

- [ ] Version đã tăng trong `pubspec.yaml` (ví dụ `1.0.1+3`)
- [ ] Version và Build khớp trong Xcode Runner → General
- [ ] `flutter test test/widget/` pass toàn bộ
- [ ] Đã test trên iPhone thật (debug build)
- [ ] `API_BASE_URL` trỏ đúng server production trong `.env.ios`
- [ ] Bundle ID là `com.semir.semirphone` trong Xcode
- [ ] `ios/ExportOptions.plist` tồn tại với Team ID đúng
- [ ] Screenshots đã cập nhật nếu UI thay đổi
- [ ] Release notes đã viết (tiếng Anh)

---

### Lỗi thường gặp

| Lỗi | Cách sửa |
|-----|----------|
| `CocoaPods not installed` | `sudo gem install cocoapods` |
| `flutter: command not found` | Chạy `brew install --cask flutter`, mở terminal mới |
| `No profiles for com.semir.semirphone` | Chạy `bundle exec fastlane match appstore` |
| `Provisioning profile doesn't include signing cert` | `bundle exec fastlane match appstore --force` |
| `No account found for apple_id` | Điền `APPLE_ID` vào `.env.ios` |
| `Upload failed: authentication credentials` | App Store Connect API key có thể đã hết hạn |
| `flutter build ipa` lỗi code signing | Mở `ios/Runner.xcworkspace` → fix signing thủ công → build lại |
| `pod install` fails | `gem install cocoapods` hoặc `cd ios && pod repo update && pod install` |
| Trust certificate trên iPhone | Settings → General → VPN & Device Management → trust |
