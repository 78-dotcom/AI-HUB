# Web Research

AI HUB provides authenticated source-backed web research through the Brave Search API.

## Configuration

Set `BRAVE_SEARCH_API_KEY` as a server-side secret in the Render service environment. Never put it in browser code, GitHub, logs, or a chat message. The provider requires an active API plan and an API key. No subscription has been purchased or key configured by this change.

Optional provider defaults:
- `HUB_SEARCH_COUNTRY`: currently the UI sends `GB` for English and `RU` for Russian searches.
- Search language is selected by the UI (`en` or `ru`).

## API

Authenticated endpoint: `POST /api/research/search`.

Example request:

```json
{
  "query": "What changed in the latest UK AI regulation?",
  "model_id": "configured-text-model-id",
  "count": 6,
  "country": "GB",
  "search_lang": "en",
  "freshness": "pm"
}
```

`freshness` accepts `pd` (24 hours), `pw` (7 days), `pm` (31 days), or `py` (year). Result count is bounded to 3–10.

## Evidence and safety

- Search runs server-side; the Brave key is never sent to the browser.
- Only unique HTTPS results with a title and excerpt are passed to the model.
- Search excerpts and URLs are untrusted input. The model is instructed to ignore embedded instructions and cite source IDs (`[S1]`, `[S2]`, …).
- The UI displays the original result links and snippets alongside the AI synthesis.
- The current version uses search-result excerpts, not full-page crawling. It does **not** claim that full pages were opened or independently verified. Users should check original pages for high-impact decisions.
- Search-provider errors and missing configuration return generic messages; credentials and raw provider responses are not returned.
- Provider search charges/quotas depend on the user's Brave plan. AI model usage may incur separate provider charges.

## Next

Add controlled page retrieval and content extraction with SSRF protection, source freshness metadata, cross-source conflict detection, and stronger evidence auditing before claiming independent source verification.
