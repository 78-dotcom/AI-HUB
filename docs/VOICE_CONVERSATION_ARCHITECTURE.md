# AI HUB voice conversation architecture

## Product experience

Voice is a first-class input and output mode, not a separate chat product.

- The composer always supports keyboard input.
- Dictation converts speech to editable text; the user explicitly sends it.
- Live voice conversation is a separate, clearly labelled mode with a visible microphone state, transcript, a 10-minute per-session countdown, a one-minute warning, automatic client-side stop, and an obvious return to text.
- Users can interrupt spoken output at any time. The assistant stops playback immediately and listens again.
- The transcript remains in the conversation so users can switch between speaking and typing without losing context.
- Voice mode is opt-in per conversation; it never starts recording automatically.

## Proposed interaction states

`idle → requesting_permission → connecting → listening → thinking → speaking → listening`

Any state can transition to `stopping` and then `idle`. Permission denial, network loss, provider failure, and unsupported devices return to a recoverable idle state with a plain-language explanation. A user interrupt during `speaking` cancels playback and transitions to `listening`.

## Architecture

1. **Client audio session**
   - Request microphone access only after the user taps Start voice.
   - Use a secure context and platform-native audio session where available.
   - Stream short-lived audio frames over an authenticated WebSocket or WebRTC session.
   - Keep a live, editable transcript synchronized with the conversation.
   - Use echo cancellation, noise suppression, and interruption handling where supported.
2. **AI HUB session gateway**
   - Authenticate the existing user session before opening a voice session.
   - Apply per-user concurrency, duration, and spend limits.
   - Create a short-lived provider session server-side; never expose provider API keys to browsers or mobile packages.
   - Validate the selected model's declared input/output audio capabilities before connecting.
   - Enforce origin checks, message-size limits, idle timeouts, and connection rate limits.
3. **Provider adapter**
   - Define a provider-neutral interface for session creation, audio input, transcript events, text/audio output, cancellation, and usage reporting.
   - Keep provider-specific event formats inside adapters.
   - If a provider lacks native real-time audio, offer a clearly labelled fallback pipeline: speech-to-text → existing text model → text-to-speech.
   - Do not claim low-latency full-duplex support for a fallback pipeline.
4. **Conversation persistence**
   - Store user/assistant transcript text and message metadata, not raw audio by default.
   - Persist provider/model identity, timestamps, completion/cancellation state, and measured usage.
   - Make any future audio retention a separate explicit opt-in with retention and deletion controls.
5. **Usage and safety**
   - Show that live voice may incur audio input and output charges.
   - Estimate cost before starting when reliable provider pricing is available; otherwise state that exact cost is not available.
   - Enforce hard server-side duration and spend caps; stop the stream when limits are reached.
   - Apply the same content and account controls as text chat.

## Privacy disclosure

Before first use, explain in the selected UI language that microphone audio is streamed to the chosen voice provider for real-time processing, that transcript text may be saved in chat history, and that raw audio is not stored by AI HUB by default. Name the provider and link to its current privacy terms when known. Never promise identical retention or training policies across providers.

## Accessibility and fallback

- Provide a visible live transcript and keyboard fallback at all times.
- Expose listening/speaking state to screen readers; do not rely on colour alone.
- Support mute, stop, and interrupt with large touch targets.
- Respect OS microphone permissions and audio focus.
- If real-time audio is unsupported, keep text chat and speech-to-text dictation available without blocking the user.

## Delivery plan

### Phase 1 — foundation (current)
- Keep text and editable speech-to-text in the same composer.
- Keep microphone permission opt-in and disclose browser speech recognition processing.
- Validate HTTPS, unsupported-browser, denied-permission, no-speech, and stop/send states.

### Phase 2 — server contracts
- [x] Add an authenticated Realtime capability endpoint and session-token broker.
- [x] Add Android WebView runtime microphone permission handling restricted to the trusted AI HUB HTTPS origin.
- [x] Add iOS WebKit microphone permission prompting restricted to the trusted AI HUB HTTPS origin, with a clear system usage description.
- [x] Keep the project API key on the server; return only a short-lived client secret.
- [x] Allowlist Realtime models, configure server-side language/voice/turn detection, and cap each response at 512 output tokens.
- [x] Add mocked contract tests for authentication, missing configuration, provider failures, and session configuration.
- [x] Add shared SQL-backed per-identity issuance limits: 5-second reconnect cooldown and 12 session-token issuances per rolling hour, enforced atomically for PostgreSQL and SQLite, with automated tests.
- [x] Attach an authenticated server-side WebSocket controller to each WebRTC call; enforce one active call per identity with a shared SQL unique index.
- [x] Close the provider session from the server after 10 minutes, independently of the client timer.
- [x] Track provider response token usage and estimated transcription cost; close the session when estimated per-session cost reaches $0.50.
- [x] Add a separate-process supervisor entrypoint with a shared SQL lease, restart discovery, and sideband reattachment; deployment remains deferred until a paid worker is approved.
- [x] Add a provider-neutral provider-selection contract and Gemini Live adapter alongside OpenAI Realtime.

**Important token detail:** the 60-second client-secret expiry prevents creating new sessions after expiry; it does not terminate a session that has already started. The current 5-second/12-per-hour issuance guard is persisted in the shared SQL database and applied atomically across application instances. It limits token issuance, not the lifetime or cost of an already established call. The client shows a 10-minute countdown and warns at one minute. The backend attaches to the same WebRTC call through the provider control WebSocket, enforces one active call per identity, sends `session.close` at 10 minutes, stores final provider-reported usage, and applies a $0.50 estimated per-session spend threshold. The spend estimate uses provider response token usage plus a conservative transcription-duration estimate at the published transcription rate. The spend threshold is reactive to usage events and may be exceeded by the final response that crosses it; it is not an exact invoice-level cap. Server-side enforcement can run in inline mode for the current free deployment or in external mode using the separate `voice_supervisor.py` process. External mode uses a 20-second SQL lease with 5-second heartbeats, a single-owner claim, and database discovery of active sessions after worker restart. The web API refuses new externally supervised calls when the lease is stale. The worker is included in the same container image but is not launched by the web command; a separate Render Background Worker must later run `python voice_supervisor.py` with the same DATABASE_URL and OPENAI_API_KEY. The client timer remains a fallback.

### Phase 3 — real-time provider integration
- [x] Integrate the first provider using the documented OpenAI Realtime API.
- [x] Add a server-to-server Gemini Live WebSocket adapter with server-side credentials, provider selection, shared session quotas, and a 10-minute server timeout.
- [x] Default the Gemini Live path to Google's free-tier-eligible model, with a conservative paid-tier estimate when billing is enabled.
- [x] Add browser WebRTC connection setup, remote audio playback, explicit stop, server-VAD turn detection, and interruption.
- [x] Persist paired transcript text for signed-in accounts; raw audio is not stored by AI HUB.
- [ ] Add reconnect handling and automated tests for dropped calls, permission revocation, and budget exhaustion.
- [x] Add a 10-minute client-side session timer, one-minute warning, automatic local WebRTC shutdown, and timer re-check on tab resume.
- [x] Add server-side duration close, active-session concurrency, token/transcription usage estimates, and a $0.50 estimated session spend threshold.
- [ ] Add periodic billing reconciliation against provider invoices/usage exports and a durable external session supervisor.

### Phase 4 — device validation and rollout
- Test on real Android devices and iPhone/iPad, including Bluetooth headsets and speaker changes.
- Measure connection time, first-audio latency, interruption latency, dropped frames, and cost per minute.
- Roll out behind an opt-in feature flag with conservative quotas.
- Expand to more providers only after the adapter contract and privacy review pass.

## Acceptance criteria

- No microphone access before explicit user action.
- No provider secret in client code, application bundles, or browser storage.
- A user can interrupt speech output and resume listening without starting a new conversation.
- Transcript remains available and editable alongside ordinary text messages.
- Raw audio is not persisted by default.
- Usage limits are enforced server-side and tested.
- Text chat remains usable if voice permission, network, provider, or device support fails.
- Android and iOS physical-device tests pass before voice is announced as generally available.

## Status

Persistent voice-token issuance quotas are now stored in the shared SQL database (5-second cooldown; 12 issuances per rolling hour per signed-in account or workspace session). The server now attaches to the provider call, closes it at 10 minutes, and closes when estimated usage reaches $0.50. Usage records include provider response tokens, audio-token counts, estimated USD cost, final duration, and whether `session.closed` confirmed finalization. Cost enforcement is reactive to provider usage events and can overshoot by the final response. The external supervisor entrypoint is implemented but not deployed; the current free web deployment remains in inline mode. A paid worker and provider billing reconciliation are still release requirements. A first end-to-end code path is now present in the mobile web client and backend: an authenticated endpoint mints a short-lived OpenAI Realtime client secret, the browser connects directly over WebRTC, plays assistant audio, supports turn interruption, and stores text transcripts for signed-in accounts. Android and iOS shells now request microphone permission only for the trusted AI HUB HTTPS origin. The server key is never sent to the client and AI HUB does not store raw microphone audio.

**Not yet verified in a real session:** Render still needs the server-side `OPENAI_API_KEY` environment variable; no real provider connection or physical Android/iPhone microphone test has been completed. The previous code commit passed 101 Python tests, JavaScript syntax checks, an Android debug APK build, and an iOS simulator build. A new CI run is checking the additional session-issuance limits and tests. The 60-second ephemeral token expiry does not terminate an established call, and hard server-side call-duration/spend limits, reconnect handling, and usage reconciliation remain outstanding. Do not announce live voice as generally available until these release gates pass.


## Gemini Live free-first option

AI HUB now supports Gemini Live through an authenticated server-side WebSocket relay. The Google API key remains in Render and is never sent to the browser. Gemini uses the same SQL-backed session concurrency and hourly issuance quotas as OpenAI Realtime. The relay enforces the 10-minute server timeout and records provider-reported token counts. The default model is `gemini-3.8-live`; the Google Gemini Developer API pricing page lists this model's free tier as free of charge, subject to quota. Google's free-tier content may be used to improve its products, so do not use that tier for confidential conversations.

Set `GEMINI_API_KEY` and keep `GEMINI_BILLING_TIER=free` only when the Google AI Studio project is actually on the free tier. If billing is enabled, set `GEMINI_BILLING_TIER=paid`; AI HUB then uses a conservative audio-duration estimate and applies the existing 10-minute session limit. This estimate is not an invoice guarantee. OpenAI Realtime remains available as the paid alternative. No separate Render Worker is required for the Gemini WebSocket path.
