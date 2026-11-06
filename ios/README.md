# AI HUB for iOS — early app shell

This is the first SwiftUI + WKWebView app shell for iPhone and iPad.

## Security and behaviour
- Loads only the AI HUB HTTPS origin inside the app.
- Opens other HTTPS websites in the system browser and blocks non-HTTPS schemes.
- Uses the system WKWebView data store for same-origin web session continuity.
- Does not embed provider API keys or other server secrets.
- Uses the web app's file input so iOS can present its system document picker when supported; no broad photo-library permission is requested.
- Includes a simple connection error and retry state.

## Build
The project is generated with XcodeGen:
`brew install xcodegen`
`xcodegen generate --spec ios/project.yml --project ios`
`xcodebuild -project ios/AIHUB.xcodeproj -scheme AIHUB -sdk iphonesimulator -configuration Debug CODE_SIGNING_ALLOWED=NO build`

This is not yet a signed App Store release or a fully native offline client. It still relies on the hosted AI HUB web experience. Physical-device testing, accessibility review, file upload/download validation, signing, privacy disclosures, and App Store policy review are required before release.

The iOS simulator build is checked by the `iOS app checks` GitHub Actions workflow. A successful simulator compile does not prove signing, App Store readiness, or physical-device behaviour.
