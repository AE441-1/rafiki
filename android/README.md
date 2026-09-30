# Rafiki Android

Native Android app for customer, bank, and insurer accounts. It includes session sign-in, role dashboards, customer loan and insurance applications, bank loan review and disbursement, and insurer policy and claim management. The client uses the Flask session cookie; it does not store account or dashboard responses offline.

## Requirements

- Android Studio with Android SDK Platform 35 and Build Tools 35
- JDK 17
- Flask backend running from the repository root

## Run on an emulator

Open this `android` folder in Android Studio and sync Gradle. Start Flask on the development computer, then build and run the `app` debug configuration. The default API address, `http://10.0.2.2:5000/`, points an Android emulator to the host computer.

From PowerShell, build a debug APK with:

```powershell
./gradlew.bat assembleDebug
```

The APK is written to `app/build/outputs/apk/debug/app-debug.apk`.

## Run on a phone over Wi-Fi

Keep the phone and development computer on the same trusted Wi-Fi network. Start a separate LAN-accessible Flask instance from the repository root:

```powershell
$env:PORT = "5001"
python app.py
```

Allow Python to accept Private-network connections if Windows Firewall prompts. Find the computer's Wi-Fi IPv4 address with `ipconfig`, then build the phone APK with that address. This computer's current address is `192.168.88.131`:

```powershell
./gradlew.bat assembleDebug -PrafikiApiBaseUrl=http://192.168.88.131:5001/
adb install app/build/outputs/apk/debug/app-debug.apk
```

The APK has the IP address embedded at build time. Rebuild it if the computer gets a different address. This HTTP/debug setup is for a trusted local network only; use HTTPS for a deployed or public release.

## Run on a USB-connected phone

With USB debugging enabled, forward the backend port:

```powershell
adb reverse tcp:5000 tcp:5000
./gradlew.bat installDebug -PrafikiApiBaseUrl=http://127.0.0.1:5000/
```

Debug builds allow cleartext HTTP for local development. Set `-PrafikiReleaseApiBaseUrl=https://your-host/` to build a release against an HTTPS deployment. The release build does not permit cleartext HTTP.

## Backend routes

- `POST /api/mobile/login`
- `GET /api/mobile/session`
- `GET /api/mobile/dashboard`
- `POST /api/mobile/logout`
- `GET|POST /api/mobile/loans`
- `GET /api/mobile/insurance/products`
- `POST /api/mobile/insurance/products/<id>/apply`
- `GET /api/mobile/bank/loan-applications`
- `POST /api/mobile/bank/loan-applications/<id>/decision`
- `POST /api/mobile/bank/loan-applications/<id>/disburse`
- `GET /api/mobile/insurer/policy-applications`
- `POST /api/mobile/insurer/policy-applications/<id>/decision`
- `GET /api/mobile/insurer/claims`
- `POST /api/mobile/insurer/claims/<id>/status`

Farm climate assessments and crop ordering are not yet implemented in the native client and remain available through the web app.