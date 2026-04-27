# Android — Google Play

---

## Part 1: Chạy local → Emulator → Thiết bị thật

### 1.1 Cài đặt môi trường (làm 1 lần)

**Flutter SDK**
1. Tải tại https://docs.flutter.dev/get-started/install/windows → giải nén vào `C:\flutter`
2. Thêm vào PATH: System Properties → Environment Variables → Path → New → `C:\flutter\bin`
3. Mở terminal mới, kiểm tra:
   ```powershell
   flutter doctor
   ```
   Mục "Android toolchain" phải có ✓ trước khi tiếp tục.

**Android Studio**
1. Tải tại https://developer.android.com/studio → cài đặt, giữ tất cả mặc định → Android Studio sẽ tự cài Android SDK
2. Mở Android Studio lần đầu → để setup wizard chạy xong
3. Cài **Command-line Tools** (bắt buộc — Flutter cần tool này):
   - Trong Android Studio: **More Actions** → **SDK Manager** → tab **SDK Tools**
   - Tích chọn **Android SDK Command-line Tools (latest)** → nhấn **OK** → chờ cài xong
4. Trỏ Flutter đến SDK:
   ```powershell
   flutter config --android-sdk "C:\Users\ASUS\AppData\Local\Android\Sdk"
   ```
5. Chấp nhận license:
   ```powershell
   flutter doctor --android-licenses
   # Bấm "y" cho tất cả câu hỏi
   ```
6. Kiểm tra:
   ```powershell
   flutter doctor
   # Android toolchain phải hiện ✓ trước khi tiếp tục
   ```

**Java (JDK 17)**
1. Tải tại https://adoptium.net → cài đặt (installer tự thêm vào PATH)
2. Kiểm tra:
   ```powershell
   java -version
   keytool -help
   ```

---

### 1.2 Tạo platform files Android (làm 1 lần)

Thư mục `android/` chưa tồn tại. Chạy lệnh này từ thư mục dự án:

```powershell
cd d:\New-jouney\semir\semir-phone
flutter create --platforms=android .
```

Lệnh này tạo ra `android/` với toàn bộ file Gradle. Code trong `lib/` không bị ảnh hưởng.

---

### 1.3 Cấu hình tên app và package name

**Tên hiển thị** — Mở `android/app/src/main/AndroidManifest.xml`, sửa dòng:
```xml
<application
    android:label="S&amp;B Dashboard"
    ...>
```

**Package name** — Mở `android/app/build.gradle`, đặt:
```gradle
android {
    defaultConfig {
        applicationId "com.semir.semirphone"
    }
}
```

---

### 1.4 Chạy trên Emulator (Android Simulator)

1. Mở Android Studio → Device Manager → **+** → Create Virtual Device → chọn Pixel 7 → API 33 → Next → Finish
2. **Nếu emulator bị crash (emulator process terminated):** Click biểu tượng bút chì (edit) cạnh Pixel 7 → Show Advanced Settings → Emulated Performance → Graphics acceleration → chọn **Software** → Finish
3. Start emulator
2. Kiểm tra emulator đã chạy:
   ```powershell
   flutter devices
   # Phải thấy: "sdk gphone64 x86 64 (mobile)"
   ```
3. Chạy app:
   ```powershell
   cd d:\New-jouney\semir\semir-phone
   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1 --dart-define=ENVIRONMENT=debug
   ```
   > `10.0.2.2` là địa chỉ đặc biệt để emulator kết nối đến localhost của máy tính.  
   > Nếu backend chạy trên server thật, dùng URL thật thay thế.

Hot reload: bấm `r` trong terminal để reload ngay mà không cần restart app.

---

### 1.5 Chạy trên thiết bị Android thật

**Bước 1 — Bật Developer Options trên điện thoại:**
- Settings → About phone → bấm "Build number" **7 lần** liên tiếp
- Settings → Developer options → bật **USB debugging**

**Bước 2 — Kết nối qua USB:**
```powershell
flutter devices
# Phải thấy tên điện thoại trong danh sách
```
Nếu không thấy: tắt/mở lại cáp USB, chọn "Trust this computer" trên màn hình điện thoại.

**Bước 3 — Tìm IP của máy tính (để app kết nối đến backend):**
```powershell
ipconfig
# Ghi lại địa chỉ IPv4, ví dụ: 192.168.1.5
```

**Bước 4 — Chạy:**
```powershell
flutter run --dart-define=API_BASE_URL=http://192.168.1.5:8000/api/v1 --dart-define=ENVIRONMENT=debug
```
> Điện thoại và máy tính phải cùng mạng WiFi.

---

### 1.6 Build APK debug để chia sẻ kiểm thử

APK debug không cần signing, có thể cài trực tiếp lên bất kỳ Android nào (không qua Play Store):

```powershell
flutter build apk --debug \
  --dart-define=API_BASE_URL=https://analytics-customer-dashboard.com/api/v1/ \
  --dart-define=ENVIRONMENT=debug
```

Output: `build\app\outputs\flutter-apk\app-debug.apk`

Gửi file này cho tester → họ cài bằng cách mở file trực tiếp trên điện thoại (bật "Install unknown apps" nếu được hỏi).

---

### 1.7 Chạy tests

```powershell
# Chạy toàn bộ widget tests (không cần thiết bị)
flutter test test/widget/

# Chạy một test cụ thể
flutter test test/widget/login_page_test.dart
```

---

## Part 2: Build release → Đẩy lên Google Play

### 2.1 Cài đặt Ruby + Fastlane (làm 1 lần)

1. Tải RubyInstaller tại https://rubyinstaller.org — chọn "Ruby+Devkit"
2. Trong quá trình cài: chạy `ridk install` khi được hỏi
3. Mở terminal mới:
   ```powershell
   gem install bundler
   cd d:\New-jouney\semir\semir-phone
   bundle install
   ```

---

### 2.2 Tạo Google Play Console app (làm 1 lần)

1. Truy cập https://play.google.com/console → **Create app**
2. App name: **S&B Dashboard**
3. Package: `com.semir.semirphone`
4. Hoàn thành store listing, content rating, pricing

---

### 2.3 Tạo keystore (signing key) — LÀM 1 LẦN DUY NHẤT

> ⚠️ **Keystore = chìa khoá duy nhất** để xác nhận app là của bạn.  
> Mất keystore = không thể update app trên Play Store mãi mãi.  
> Lưu file `.jks` và 2 password vào password manager ngay sau khi tạo.

```powershell
keytool -genkey -v `
  -keystore C:\keys\semir.jks `
  -alias semirphone `
  -keyalg RSA -keysize 2048 -validity 10000
```

Sẽ được hỏi:
- Keystore password → nhập password mạnh, ghi nhớ
- Key password → có thể dùng cùng password
- Tên, tổ chức, thành phố, quốc gia → điền tuỳ ý

---

### 2.4 Cấu hình signing trong app (làm 1 lần)

Tạo file `android/key.properties` (file này đã được gitignore, không commit):
```properties
storeFile=C:\\keys\\semir.jks
storePassword=your-keystore-password
keyAlias=semirphone
keyPassword=your-key-password
```

Mở `android/app/build.gradle`, thêm đoạn sau:
```gradle
// Thêm TRƯỚC khối android {}
def keystoreProperties = new Properties()
def keystorePropertiesFile = rootProject.file('key.properties')
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(new FileInputStream(keystorePropertiesFile))
}

android {
    signingConfigs {
        release {
            keyAlias     keystoreProperties['keyAlias']
            keyPassword  keystoreProperties['keyPassword']
            storeFile    keystoreProperties['storeFile'] ? file(keystoreProperties['storeFile']) : null
            storePassword keystoreProperties['storePassword']
        }
    }
    buildTypes {
        release {
            signingConfig  signingConfigs.release
            minifyEnabled  true
            shrinkResources true
        }
    }
}
```

---

### 2.5 Tạo service account để Fastlane upload tự động (làm 1 lần)

1. Play Console → Setup → API access → Link to Google Cloud project
2. Google Cloud Console → IAM & Admin → Service Accounts → **Create service account**
3. Grant role: **Release Manager**
4. Keys → Add key → JSON → Download file `.json`
5. Play Console → Grant access → thêm email của service account

---

### 2.6 Cấu hình secrets

```powershell
copy scripts\.env.android.template .env.android
notepad .env.android   # điền tất cả các giá trị
```

| Biến | Lấy ở đâu |
|------|-----------|
| `KEYSTORE_PATH` | Đường dẫn tuyệt đối đến file `.jks` (bước 2.3) |
| `KEYSTORE_PASS` | Password keystore (bước 2.3) |
| `KEY_ALIAS` | `semirphone` |
| `KEY_PASS` | Key password (bước 2.3) |
| `PLAY_STORE_JSON_KEY` | Dán toàn bộ nội dung file JSON (bước 2.5) |
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

---

### 2.8 Build AAB và upload lên Play Store

```bash
# Chạy trong Git Bash hoặc WSL (không phải PowerShell)
bash scripts/deploy_android.sh

# Upload thẳng lên Production (bỏ qua Internal Testing):
bash scripts/deploy_android.sh production
```

Script tự động:
1. Load secrets từ `.env.android`
2. Hỏi có muốn tăng build number không
3. `flutter clean && flutter pub get`
4. Chạy toàn bộ widget tests (dừng nếu có test fail)
5. Build signed AAB
6. Upload lên Play Store Internal Testing

---

### 2.9 Sau khi upload — promote lên Production

1. Play Console → S&B Dashboard → Testing → Internal testing
2. Chọn build vừa upload → **Promote to Production**
3. Đặt rollout **10%** trước, theo dõi 1–2 ngày
4. Tăng lên 50% → 100% nếu không có crash

**Theo dõi crash:** Play Console → Android vitals → Crashes & ANRs  
Mục tiêu: crash-free sessions > 99.5%

---

### Checklist mỗi lần release

- [ ] Build number đã tăng trong `pubspec.yaml`
- [ ] `flutter test test/widget/` pass toàn bộ
- [ ] Đã test trên thiết bị Android thật (debug build)
- [ ] `API_BASE_URL` trỏ đúng server production
- [ ] File `.jks` có thể truy cập tại `KEYSTORE_PATH`

---

### Lỗi thường gặp

| Lỗi | Cách sửa |
|-----|----------|
| `flutter: command not found` | Thêm `C:\flutter\bin` vào PATH, mở terminal mới |
| `Android license status unknown` | Chạy `flutter doctor --android-licenses` |
| `Android sdkmanager not found` | Mở Android Studio → SDK Manager → SDK Tools → tích **Android SDK Command-line Tools (latest)** → OK. Sau đó chạy `flutter config --android-sdk "C:\Users\ASUS\AppData\Local\Android\Sdk"` |
| `Emulator process terminated` (crash khi start) | Edit AVD → Show Advanced Settings → Graphics acceleration → chọn **Software** → Finish → Start lại |
| `Unable to locate Android SDK` | Chạy `flutter config --android-sdk "C:\Users\ASUS\AppData\Local\Android\Sdk"` |
| `keytool: command not found` | Cài JDK 17, mở terminal mới |
| `Keystore file not found` | Kiểm tra `KEYSTORE_PATH` trong `.env.android` — dùng đường dẫn tuyệt đối |
| `Package not found` trên upload | App chưa được tạo trong Play Console, hoặc package name sai |
| `401 Unauthorized` khi upload | Service account JSON hết hạn hoặc thiếu quyền |
