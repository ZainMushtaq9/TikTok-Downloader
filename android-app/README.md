# Xainvex Android App

A WebView-based Android app that wraps the Xainvex video downloader website. Includes Google AdMob for mobile ad revenue.

## How to Build

### Option 1: Android Studio (Recommended)
1. Open Android Studio
2. Open this `android-app` folder as a project
3. Wait for Gradle to sync
4. Click **Run** → Select your device/emulator
5. Build APK: **Build** → **Build Bundle(s)/APK(s)** → **Build APK(s)**

### Option 2: Command Line
```bash
cd android-app
./gradlew assembleRelease
```

### Option 3: Online APK Builder (No Android Studio Needed)
Use one of these free services to convert the web app to APK directly:
1. **[AppsGeyser.com](https://appsgeyser.com)** — Paste your URL, customize, and get APK in minutes
2. **[WebIntoApp.com](https://webintoapp.com)** — Free WebView app builder
3. **[Gonative.io](https://gonative.io)** — More advanced, supports push notifications

### Configuration
- **Website URL**: Set in `app/src/main/java/com/xainvex/app/MainActivity.java`
- **AdMob App ID**: Set in `app/src/main/AndroidManifest.xml`
- **AdMob Banner ID**: Set in `activity_main.xml`
- **App Icon**: Replace files in `app/src/main/res/mipmap-*/ic_launcher.png`

### AdMob Setup
1. Create account at [admob.google.com](https://admob.google.com)
2. Create a new app → Get your App ID (ca-app-pub-xxx~xxx)
3. Create a Banner ad unit → Get your Ad Unit ID
4. Replace the test IDs in the code with your real IDs
