# AI HUB mobile product and security principles

## Product direction

AI HUB should feel like one calm, capable workspace rather than a crowded directory of AI features. The home screen stays focused on starting a task, choosing Auto or a model, and continuing recent work. Advanced capabilities live in a clearly named Tools area and open only when requested.

The product should combine proven patterns from multi-model assistants without copying their visual identity:

- **Model choice and comparison:** make provider/model identity visible; offer Auto for convenience and explicit model selection for control. Add side-by-side model comparison only when the user asks for it, and show which model produced each answer.
- **Useful assistant ecosystem:** searchable, categorized assistants; clear creator, purpose, and permissions; private by default; public sharing is a deliberate action.
- **Context and long-running work:** project spaces with files, notes, and user-controlled memory; explain what context is used and let users inspect, pause, or delete it.
- **Transparent usage:** show provider/model, token usage when available, and cost only when real pricing data supports it. Warn before multi-model workflows that make multiple paid calls.
- **Research and verification:** show sources for web research; distinguish source-backed facts from model reasoning and uncertainty.
- **File-first productivity:** let users attach supported files through the system picker, display extraction status and truncation, and never imply that an image or file was processed if it was not.
- **Cross-device continuity:** one account and server-side history across web, Android, and iOS; mobile navigation must expose history, new chat, tools, and settings without hiding core tasks.

Poe's documented strengths worth learning from include multi-model access, model comparison, custom bots, context controls, transparent point/cost information, and per-bot privacy indicators. AI HUB should adopt the underlying usability patterns while making provider data flows and permissions explicit. See Poe's [product FAQ](https://help.poe.com/hc/en-us/articles/19944206309524-Poe-FAQs) and [Privacy Center](https://poe.com/pages/privacy-center).

## UX rules

1. Keep the main chat composer visible and reachable with one hand.
2. Use a mobile history drawer with search; do not hide conversation history on phones.
3. Keep advanced tools grouped, searchable, and out of the primary path until needed.
4. Provide clear empty, loading, success, error, and offline states.
5. Support keyboard-safe layouts, safe-area insets, large touch targets, screen readers, and visible focus.
6. Provide copy, retry, rename, archive, export, and delete actions with confirmation for destructive operations.
7. Keep English as the initial international UI language and support Russian without layout breakage; add languages through translation dictionaries rather than hard-coded UI strings.
8. Prefer predictable navigation and fast startup over decorative animation.

## Privacy and security baseline

Use OWASP MASVS as the mobile security acceptance framework, covering storage, cryptography, authentication, network, platform, code quality, resilience, and privacy. Use the [MASVS](https://mas.owasp.org/MASVS/) and [Mobile Application Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mobile_Application_Security_Cheat_Sheet.html) as implementation references.

- **Provider transparency:** before sending a prompt or extracted attachment text, tell the user it is sent to the selected AI provider. Never promise that all providers have identical retention or training policies.
- **Privacy indicators:** show whether a tool/assistant sends content to an external provider, developer endpoint, or web service; explain each permission before enabling it. Public assistants must be private by default until the owner opts in.
- **Data minimization:** request device permissions only at the moment a feature needs them. Use Android Photo Picker / system document picker and iOS document/photo pickers instead of broad library access.
- **Secrets:** provider API keys remain server-side. Never embed provider credentials or admin secrets in Android/iOS packages, web assets, logs, or analytics.
- **Transport:** HTTPS only; reject invalid certificates; do not cache API responses, prompts, files, auth state, or private chat content in the service worker.
- **Authentication:** server-side authorization on every private resource; revocable sessions; secure cookies/tokens; session expiry and remote logout. OAuth on native apps must use system authentication sessions rather than embedded WebViews.
- **Local storage:** do not store passwords or long-lived bearer tokens in ordinary preferences/localStorage. Use Android Keystore and iOS Keychain for native secrets. Keep private history server-side for signed-in users; any offline cache must be opt-in, encrypted, and clearable.
- **Privacy controls:** offer temporary chats, per-chat deletion, full export, account deletion, memory review/pause/delete, and clear retention disclosures before public launch.
- **Abuse and cost controls:** server-side rate limits, quotas, file limits, provider timeouts, request IDs, and hard budget enforcement based on actual provider billing data where available.
- **Secure release:** signed builds, dependency scanning, least-privilege permissions, no debug flags in release, SBOM, and MASVS-based tests on physical devices.

## Release gates

Do not call the app production-ready until all of the following pass:

- Android and iOS sign-in/session lifecycle tests, including logout and expired sessions.
- Cross-device conversation sync and ownership/isolation tests.
- Upload validation, oversized/malformed file tests, and safe file picker behaviour.
- Network inspection confirming HTTPS-only and no sensitive API/service-worker caching.
- Accessibility, keyboard, screen-size, orientation, and screen-reader checks.
- Dependency/security scans and MASVS checklist review.
- Signed release artifacts and tested update/rollback procedure.
- Privacy policy, provider disclosure, retention, export, and deletion flows are accurate and working.

## Current implementation status

The current branch contains an installable web app foundation, an early Android WebView shell, and an early SwiftUI/WKWebView iOS shell. The mobile history drawer, copy-answer action, provider disclosure, and system document pickers are early UX improvements. These are not proof of complete security or native feature parity. CI builds are compile checks only; physical-device testing, iOS simulator build verification, robust account controls, and the release gates above remain outstanding.
