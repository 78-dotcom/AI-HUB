-- Match-Factor v2.3 data foundation
-- PostgreSQL schema. Apply explicitly; this file is not run automatically at app startup.

CREATE TABLE IF NOT EXISTS mf_sources (
    id BIGSERIAL PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    licence TEXT,
    attribution TEXT,
    commercial_use_allowed BOOLEAN,
    terms_checked_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mf_ingestion_runs (
    id BIGSERIAL PRIMARY KEY,
    source_key TEXT NOT NULL REFERENCES mf_sources(source_key),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    file_name TEXT,
    file_sha256 TEXT,
    rows_seen INTEGER NOT NULL DEFAULT 0,
    rows_processed INTEGER NOT NULL DEFAULT 0,
    rows_updated INTEGER NOT NULL DEFAULT 0,
    rows_rejected INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    error_summary TEXT
);

CREATE TABLE IF NOT EXISTS mf_events (
    id BIGSERIAL PRIMARY KEY,
    sport TEXT NOT NULL,
    competition TEXT,
    season TEXT,
    event_start_utc TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    surface TEXT,
    round_name TEXT,
    source_key TEXT NOT NULL REFERENCES mf_sources(source_key),
    external_id TEXT NOT NULL,
    raw_record JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_key, external_id)
);
CREATE INDEX IF NOT EXISTS ix_mf_events_sport_start ON mf_events(sport, event_start_utc);

CREATE TABLE IF NOT EXISTS mf_participants (
    id BIGSERIAL PRIMARY KEY,
    sport TEXT NOT NULL,
    participant_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mf_participant_aliases (
    id BIGSERIAL PRIMARY KEY,
    participant_id BIGINT NOT NULL REFERENCES mf_participants(id) ON DELETE CASCADE,
    source_key TEXT NOT NULL REFERENCES mf_sources(source_key),
    external_id TEXT NOT NULL,
    name_as_seen TEXT NOT NULL,
    UNIQUE (source_key, external_id)
);

CREATE TABLE IF NOT EXISTS mf_event_participants (
    event_id BIGINT NOT NULL REFERENCES mf_events(id) ON DELETE CASCADE,
    participant_id BIGINT NOT NULL REFERENCES mf_participants(id),
    role TEXT NOT NULL,
    source_external_id TEXT,
    PRIMARY KEY (event_id, role)
);

CREATE TABLE IF NOT EXISTS mf_results (
    event_id BIGINT PRIMARY KEY REFERENCES mf_events(id) ON DELETE CASCADE,
    winner_participant_id BIGINT REFERENCES mf_participants(id),
    final_score TEXT,
    duration_minutes INTEGER,
    source_key TEXT NOT NULL REFERENCES mf_sources(source_key),
    raw_record JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS mf_odds_snapshots (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES mf_events(id) ON DELETE CASCADE,
    source_key TEXT NOT NULL REFERENCES mf_sources(source_key),
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,
    selection TEXT NOT NULL,
    line NUMERIC(12,4),
    decimal_odds NUMERIC(12,6) NOT NULL CHECK (decimal_odds > 1),
    captured_at TIMESTAMPTZ,
    snapshot_stage TEXT NOT NULL CHECK (snapshot_stage IN ('opening', 'closing', 'observed')),
    is_opening BOOLEAN NOT NULL DEFAULT FALSE,
    is_closing BOOLEAN NOT NULL DEFAULT FALSE,
    raw_record JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (event_id, source_key, bookmaker, market, selection, snapshot_stage)
);
CREATE INDEX IF NOT EXISTS ix_mf_odds_event_market_time ON mf_odds_snapshots(event_id, market, captured_at);

CREATE TABLE IF NOT EXISTS mf_stat_snapshots (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES mf_events(id) ON DELETE CASCADE,
    participant_id BIGINT REFERENCES mf_participants(id),
    source_key TEXT NOT NULL REFERENCES mf_sources(source_key),
    captured_at TIMESTAMPTZ NOT NULL,
    valid_as_of TIMESTAMPTZ NOT NULL,
    stats JSONB NOT NULL,
    UNIQUE (event_id, participant_id, source_key, captured_at)
);

CREATE TABLE IF NOT EXISTS mf_availability_snapshots (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES mf_events(id) ON DELETE CASCADE,
    participant_id BIGINT NOT NULL REFERENCES mf_participants(id),
    source_key TEXT NOT NULL REFERENCES mf_sources(source_key),
    captured_at TIMESTAMPTZ NOT NULL,
    valid_as_of TIMESTAMPTZ NOT NULL,
    availability_status TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (event_id, participant_id, source_key, captured_at)
);

CREATE TABLE IF NOT EXISTS mf_raw_records (
    id BIGSERIAL PRIMARY KEY,
    source_key TEXT NOT NULL REFERENCES mf_sources(source_key),
    external_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    payload_sha256 TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ingestion_run_id BIGINT REFERENCES mf_ingestion_runs(id),
    UNIQUE (source_key, external_id, payload_sha256)
);
