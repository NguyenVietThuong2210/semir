# iOS — App Store

> ⚠️ **Bắt buộc phải có Mac với macOS 13+. Không thể build iOS trên Windows.**

---

## Part 1: Cài đặt môi trường (Mac mới, chưa có gì)

### 1.1 Cài Homebrew (package manager cho Mac)

Mở **Terminal** (Spotlight → gõ "Terminal" → Enter):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Làm theo hướng dẫn trên màn hình (sẽ hỏi password của Mac). Sau khi xong:

```bash
# Nếu dùng chip Apple Silicon (M1/M2/M3), chạy thêm lệnh này:
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"

# Kiểm tra
brew --version
```

---

### 1.2 Cài Git

```bash
brew install git

# Kiểm tra
git --version

# Cấu hình tên và email (dùng 1 lần)
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```

---

### 1.3 Cài Xcode

1. Mở **App Store** trên Mac → tìm **"Xcode"** → nhấn **Get** → **Install**
   > Khoảng 15 GB, mất 30–60 phút tuỳ tốc độ mạng

2. Sau khi cài xong, mở Xcode một lần để nó cài thêm components → chờ xong → đóng lại

3. Chấp nhận license:
   ```bash
   sudo xcodebuild -license accept
   # Nhập password Mac → gõ "agree" → Enter
   ```

4. Cài command-line tools:
   ```bash
   xcode-select --install
   # Một cửa sổ sẽ hiện ra → nhấn Install → chờ xong
   ```

5. Kiểm tra:
   ```bash
   xcode-select -p
   # Phải in ra: /Applications/Xcode.app/Contents/Developer
   ```

---

### 1.4 Cài Flutter SDK

```bash
brew install --cask flutter

# Mở terminal mới, kiểm tra
flutter --version
```

Nếu `flutter: command not found`, thêm vào PATH:

```bash
echo 'export PATH="$PATH:/opt/homebrew/bin"' >> ~/.zshrc
source ~/.zshrc
flutter --version
```

---

### 1.5 Cài CocoaPods (dependency manager cho iOS)

```bash
sudo gem install cocoapods

# Kiểm tra
pod --version   # in ra số version là OK
```

Nếu báo lỗi permission:
```bash
brew install rbenv ruby-build
rbenv install 3.2.0
rbenv global 3.2.0
echo 'eval "$(rbenv init -)"' >> ~/.zshrc
source ~/.zshrc
gem install cocoapods
```

---

### 1.6 Cài Ruby + Bundler (dùng cho Fastlane ở Part 2)

```bash
brew install rbenv ruby-build

# Cài Ruby 3.2.0
rbenv install 3.2.0
rbenv global 3.2.0

# Thêm vào shell profile
echo 'eval "$(rbenv init -)"' >> ~/.zshrc
source ~/.zshrc

# Kiểm tra
ruby --version   # phải thấy 3.2.0

# Cài Bundler
gem install bundler
```

---

### 1.7 Chạy flutter doctor — kiểm tra toàn bộ

```bash
flutter doctor
```

Kết quả mong đợi — **tất cả phải có ✓**:

```
[✓] Flutter
[✓] Xcode
[✓] Chrome (không bắt buộc)
[✓] Android toolchain (không bắt buộc cho iOS)
[✓] CocoaPods
```

Nếu có mục nào ✗, đọc thông báo lỗi và làm theo hướng dẫn của nó.

---

## Part 2: Lấy code và cấu hình project

### 2.1 Clone project về Mac

```bash
# Tạo thư mục làm việc
mkdir -p ~/Projects
cd ~/Projects

# Clone repo
git clone <repo-url> semir
cd semir/semir-phone

# Cài dependencies Flutter
flutter pub get
```

---

### 2.2 Tạo platform files iOS (làm 1 lần)

Thư mục `ios/` chưa tồn tại. Chạy từ thư mục `semir-phone/`:

```bash
cd ~/Projects/semir/semir-phone
flutter create --platforms=ios .
```

> Lệnh này tạo `ios/` với toàn bộ Xcode project. Code trong `lib/` không bị ảnh hưởng.

Cài iOS dependencies:
```bash
cd ios && pod install && cd ..
```

> Lần đầu `pod install` có thể mất 5–10 phút.

---

### 2.3 Cấu hình tên app và Bundle ID

**Tên hiển thị** — mở `ios/Runner/Info.plist`, thêm 2 key vào trong `<dict>` gốc:

```xml
<key>CFBundleDisplayName</key>
<string>S&amp;B Dashboard</string>
<key>CFBundleName</key>
<string>SandBDashboard</string>
```

**Bundle ID** — mở Xcode:

```bash
open ios/Runner.xcworkspace
```

Trong Xcode:
1. Click **Runner** ở sidebar trái
2. Chọn target **Runner** → tab **General**
3. **Bundle Identifier**: `com.semir.semirphone`
4. **Version**: `1.0.0` — **Build**: `1` (phải khớp `pubspec.yaml`)
5. **⌘S** để lưu → đóng Xcode

---

## Part 3: Chạy app local

### 3.1 Chạy trên iOS Simulator

```bash
# Mở Simulator
open -a Simulator

# Kiểm tra Flutter thấy simulator
flutter devices
# Phải thấy: "iPhone ## (simulator)"

# Chạy app (kết nối backend trên cùng máy Mac)
cd ~/Projects/semir/semir-phone
flutter run \
  --dart-define=API_BASE_URL=http://localhost:8000/api/v1 \
  --dart-define=ENVIRONMENT=debug
```

> Bấm **`r`** trong terminal để hot reload — app cập nhật ngay không cần restart.

**Chọn simulator khác:**
```bash
# Xem danh sách simulator
flutter emulators

# Chạy trên simulator cụ thể
flutter emulators --launch apple_ios_simulator
```

---

### 3.2 Chạy trên iPhone thật

**Bước 1 — Thêm Apple ID vào Xcode:**
- Xcode → **Settings** (⌘,) → **Accounts** → **+** → Apple ID → đăng nhập

**Bước 2 — Cắm iPhone qua cáp Lightning/USB-C:**
- iPhone hiện thông báo "Trust This Computer?" → nhấn **Trust** → nhập passcode iPhone

**Bước 3 — Kiểm tra Flutter thấy iPhone:**
```bash
flutter devices
# Phải thấy tên iPhone trong danh sách
```

**Bước 4 — Cấu hình signing trong Xcode:**
```bash
open ios/Runner.xcworkspace
```
- Click **Runner** → tab **Signing & Capabilities**
- Tích **Automatically manage signing**
- Chọn **Team** (Apple ID của bạn)
- Xcode sẽ tự tạo provisioning profile

**Bước 5 — Tìm IP của Mac:**
```bash
ifconfig | grep "inet 192"
# Ghi lại địa chỉ, ví dụ: 192.168.1.10
```

**Bước 6 — Chạy:**
```bash
flutter run \
  --dart-define=API_BASE_URL=http://192.168.1.10:8000/api/v1 \
  --dart-define=ENVIRONMENT=debug
```

> iPhone và Mac phải cùng mạng WiFi.

**Lần đầu chạy trên iPhone:** vào **Settings → General → VPN & Device Management** → trust certificate của developer.

---

### 3.3 Chạy tests

```bash
# Toàn bộ tests (không cần thiết bị)
cd ~/Projects/semir/semir-phone
flutter test

# Widget tests
flutter test test/widget/

# Một test cụ thể
flutter test test/widget/login_page_test.dart

# Cập nhật golden images (sau khi thay đổi UI)
flutter test test/golden/golden_test.dart --update-goldens
```

---

## Part 4: Build release → Đẩy lên App Store

### 4.1 Đăng ký Apple Developer Program (làm 1 lần — $99/năm)

1. Truy cập https://developer.apple.com → nhấn **Enroll**
2. Chọn Individual (cá nhân) hoặc Organization (công ty)
3. Thanh toán $99/năm bằng thẻ tín dụng
4. Quá trình duyệt mất **1–2 ngày làm việc**

---

### 4.2 Tạo App ID (làm 1 lần)

1. Truy cập https://developer.apple.com → **Account** → **Certificates, Identifiers & Profiles**
2. **Identifiers** → **+** → **App IDs** → **App** → Continue
3. Description: `SemirPhone`
4. Bundle ID: chọn **Explicit** → nhập `com.semir.semirphone`
5. Capabilities: giữ mặc định → **Register**

---

### 4.3 Tạo app trên App Store Connect (làm 1 lần)

1. Truy cập https://appstoreconnect.apple.com
2. **My Apps** → **+** → **New App**
3. Platform: **iOS**
4. Name: **S&B Dashboard**
5. Primary Language: English
6. Bundle ID: chọn `com.semir.semirphone` (từ bước 4.2)
7. SKU: `semirphone`
8. User Access: Full Access → **Create**

---

### 4.4 Cài Fastlane

```bash
cd ~/Projects/semir/semir-phone
bundle install
```

Nếu chưa có `Gemfile`, tạo file `Gemfile`:
```ruby
source "https://rubygems.org"
gem "fastlane"
```

Rồi chạy:
```bash
bundle install
```

---

### 4.5 Tạo certificates với Fastlane Match (làm 1 lần)

Match lưu certificate vào private git repo để dùng chung và tránh mất certificate.

**Bước 1 — Tạo private repo chứa certificates:**
- GitHub → **New repository** → tên: `semir-certs` → chọn **Private** → **Create repository**

**Bước 2 — Khởi tạo Match:**
```bash
cd ~/Projects/semir/semir-phone
bundle exec fastlane match init
# Chọn: git
# Nhập SSH URL của repo: git@github.com:<your-username>/semir-certs.git
```

**Bước 3 — Tạo App Store certificate:**
```bash
bundle exec fastlane match appstore
# Nhập password mạnh khi được hỏi
# → lưu password này ngay vào password manager (đây là MATCH_PASSWORD)
```

---

### 4.6 Tạo file ExportOptions.plist (làm 1 lần)

**Tìm Team ID:**
- https://developer.apple.com → **Account** → **Membership Details** → ghi lại **Team ID** (dạng `AB12CD34EF`)

Tạo file `ios/ExportOptions.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>app-store</string>
    <key>teamID</key>
    <string>AB12CD34EF</string>
    <key>uploadBitcode</key>
    <false/>
    <key>uploadSymbols</key>
    <true/>
    <key>compileBitcode</key>
    <false/>
</dict>
</plist>
```

> Thay `AB12CD34EF` bằng Team ID thật của bạn.

---

### 4.7 Cấu hình secrets (làm 1 lần)

```bash
cp scripts/.env.ios.template .env.ios
nano .env.ios
```

| Biến | Lấy ở đâu |
|------|-----------|
| `APPLE_ID` | Email đăng ký Apple Developer |
| `ITC_TEAM_ID` | App Store Connect → Users → chọn account → cuộn xuống → Team ID (toàn số) |
| `APPLE_TEAM_ID` | developer.apple.com → Account → Membership → Team ID (chữ + số, ví dụ `AB12CD34EF`) |
| `MATCH_GIT_URL` | SSH URL của repo `semir-certs` (bước 4.5) |
| `MATCH_PASSWORD` | Password đặt trong bước 4.5 |
| `API_BASE_URL` | `https://analytics-customer-dashboard.com/api/v1/` |

---

### 4.8 Tăng version trước mỗi lần release

Mở `pubspec.yaml`, tăng build number:
```yaml
version: 1.0.0+1   # lần đầu
version: 1.0.0+2   # lần 2 (bắt buộc tăng dù code không đổi)
version: 1.0.1+3   # bug fix
version: 1.1.0+4   # tính năng mới
```

Đồng bộ vào Xcode: **Runner → General → Version** và **Build** phải khớp với `pubspec.yaml`.

---

### 4.9 Build IPA và upload lên TestFlight

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
5. Chạy toàn bộ tests — dừng nếu có test fail
6. Sync certificates qua Fastlane Match
7. Build signed IPA (`flutter build ipa`)
8. Upload lên TestFlight

---

### 4.10 TestFlight testing

1. App Store Connect → **S&B Dashboard** → **TestFlight**
2. Thêm internal testers (Apple ID của team)
3. Họ nhận email → cài app **TestFlight** → cài **S&B Dashboard**

> Build processing mất **5–15 phút** sau khi upload.

**Checklist test TestFlight:**
- [ ] App khởi động không crash
- [ ] Đăng nhập → hiển thị đúng username
- [ ] Trang Sales load dữ liệu trong 4 giây (WiFi)
- [ ] Customer Lookup: tìm theo số điện thoại → hiện số đã mask
- [ ] Store Detail: chọn cửa hàng → đủ 3 section load
- [ ] Đăng xuất → quay về màn login
- [ ] Kill app → mở lại → vẫn còn đăng nhập (session persist)
- [ ] Không có crash trong App Store Connect → TestFlight → Crashes

---

### 4.11 Submit lên App Store

Sau khi TestFlight pass:

```bash
bash scripts/deploy_ios.sh release
```

Trên App Store Connect:
1. **S&B Dashboard** → **App Store** → **+** Version
2. Chọn build vừa upload từ TestFlight
3. Viết release notes (tiếng Anh)
4. Thêm screenshots (bắt buộc: **6.5" iPhone** và **5.5" iPhone**)
5. **Submit for Review**

> Apple review thường mất **24–48 giờ**.

---

## Checklist mỗi lần release

- [ ] Version đã tăng trong `pubspec.yaml`
- [ ] Version và Build khớp trong Xcode Runner → General
- [ ] `flutter test` pass toàn bộ 198 tests
- [ ] Đã test trên iPhone thật (debug build)
- [ ] `API_BASE_URL` trỏ đúng server production trong `.env.ios`
- [ ] Bundle ID là `com.semir.semirphone` trong Xcode
- [ ] `ios/ExportOptions.plist` tồn tại với Team ID đúng
- [ ] Screenshots đã cập nhật nếu UI thay đổi
- [ ] Release notes đã viết (tiếng Anh)

---

## Lỗi thường gặp

| Lỗi | Cách sửa |
|-----|----------|
| `brew: command not found` | Chạy lại lệnh cài Homebrew ở bước 1.1 |
| `flutter: command not found` | Mở terminal mới sau khi cài; hoặc `source ~/.zshrc` |
| `xcode-select: error` | Chạy `xcode-select --install` và chờ xong |
| `CocoaPods not installed` | `sudo gem install cocoapods` |
| `pod install` fails | `cd ios && pod repo update && pod install` |
| `No profiles for com.semir.semirphone` | `bundle exec fastlane match appstore` |
| `Provisioning profile doesn't include signing cert` | `bundle exec fastlane match appstore --force` |
| `No account found for apple_id` | Điền `APPLE_ID` vào `.env.ios` |
| `Upload failed: authentication credentials` | App Store Connect API key hết hạn — tạo lại |
| `flutter build ipa` lỗi code signing | `open ios/Runner.xcworkspace` → Signing & Capabilities → fix thủ công → build lại |
| Trust certificate trên iPhone | Settings → General → VPN & Device Management → trust |
| `ruby: command not found` | `brew install rbenv ruby-build` → `rbenv install 3.2.0` → `rbenv global 3.2.0` → `source ~/.zshrc` |
