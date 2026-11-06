# AI HUB voice conversation architecture

## Product experience

Voice is a first-class input and output mode, not a separate chat product.

- The composer always supports keyboard input.
- Dictation converts speech to editable text; the user explicitly sends it.
- Live voice conversation is a separate, clearly labelled mode with a visible microphone state, transcript, mute/stop controls, and an obvious return to text.
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
- [ ] Add per-user concurrency, session-duration, and spend enforcement before public rollout.
- [ ] Add a provider-neutral adapter interface before expanding beyond the first provider.

**Important token detail:** the 60-second client-secret expiry prevents creating new sessions after expiry; it does not terminate a session that has already started. It is not a hard session-duration or spend cap. The client must always provide a visible Stop control, and server-side usage/budget enforcement remains a release requirement.

### Phase 3 — real-time provider integration
- [x] Integrate the first provider using the documented OpenAI Realtime API.
- [x] Add browser WebRTC connection setup, remote audio playback, explicit stop, server-VAD turn detection, and interruption.
- [x] Persist paired transcript text for signed-in accounts; raw audio is not stored by AI HUB.
- [ ] Add reconnect handling and automated tests for dropped calls, permission revocation, and budget exhaustion.
- [ ] Add usage reconciliation and hard server-side duration/spend controls.

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

A first end-to-end code path is now present in the mobile web client and backend: an authenticated endpoint mints a short-lived OpenAI Realtime client secret, the browser connects directly over WebRTC, plays assistant audio, supports turn interruption, and stores text transcripts for signed-in accounts. Android and iOS shells now request microphone permission only for the trusted AI HUB HTTPS origin. The server key is never sent to the client and AI HUB does not store raw microphone audio.

**Not yet verified in a real session:** Render still needs the server-side `OPENAI_API_KEY` environment variable; no real provider connection or physical Android/iPhone microphone test has been completed. Earlier CI on the previous UI commit passed 101 Python tests, JavaScript syntax checks, and an iOS simulator build; the latest native microphone changes are being rechecked. The 60-second ephemeral token expiry does not terminate an established call, and hard server-side call-duration/spend limits, reconnect handling, and usage reconciliation remain outstanding. Do not announce live voice as generally available until these release gates pass.
