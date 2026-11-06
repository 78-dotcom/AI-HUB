# AI HUB Android app (early access)

This is the first native Android shell for the existing AI HUB service. It opens the hosted application in Android System WebView, preserving the same HTTPS origin for API requests, sign-in cookies, and browser storage. The app does not contain provider API keys or a second account database.

## Build a debug APK

Requirements: JDK 17 and Gradle 8.9.

From the repository root:

    gradle --no-daemon -p android :app:assembleDebug

APK output: android/app/build/outputs/apk/debug/app-debug.apk.

GitHub Actions builds and uploads this debug APK for pull requests that change the Android project. This is a development build, not a signed release for Google Play.

## App behaviour and security

- Loads only https://ai-hub-w6h6.onrender.com inside the app WebView.
- Opens other HTTP(S) links in the device browser; blocks other URL schemes.
- JavaScript and DOM storage are enabled because the existing AI HUB web client requires them.
- File/content access and cleartext HTTP are disabled; mixed content is blocked.
- API routes are not cached by the service worker.

## Release status

This is an early Android shell around the hosted web experience, not a fully native offline AI client. Before public distribution, the team must test sign-in, cookies, file upload/download, keyboard behaviour, navigation, accessibility, and current Android versions on physical devices; add a branded launcher icon and signed release configuration; and review Google Play policy requirements. iOS packaging is a separate next milestone.
