-- ============================================
-- Multi-Agentic AI Enterprise OS
-- Database Initialization Script
-- ============================================
-- This runs automatically on first PostgreSQL start

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create department schemas for data isolation
CREATE SCHEMA IF NOT EXISTS enterprise;
CREATE SCHEMA IF NOT EXISTS tech;
CREATE SCHEMA IF NOT EXISTS finance;
CREATE SCHEMA IF NOT EXISTS hr;
CREATE SCHEMA IF NOT EXISTS sales;
CREATE SCHEMA IF NOT EXISTS marketing;
CREATE SCHEMA IF NOT EXISTS legal;
CREATE SCHEMA IF NOT EXISTS bizdev;

-- Grant usage to public (app uses RLS for row-level isolation)
GRANT USAGE ON SCHEMA enterprise, tech, finance, hr, sales, marketing, legal, bizdev TO postgres;

-- ═══════════════════════════════════════════════════════════════
--  AUDIT EVENTS (append-only event log)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS audit_events (
  id                 VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,

  -- correlation
  trace_id           VARCHAR(36) NOT NULL,
  span_id            VARCHAR(36),
  parent_span_id     VARCHAR(36),

  -- who/where
  department         VARCHAR(50)  NOT NULL,
  agent_id           VARCHAR(255) NOT NULL,
  agent_role         VARCHAR(50)  NOT NULL DEFAULT 'agent',
  requester_id       VARCHAR(100),
  environment        VARCHAR(20)  NOT NULL DEFAULT 'prod',

  -- what happened
  event_type         VARCHAR(100) NOT NULL,
  status             VARCHAR(50),
  decision           VARCHAR(50),

  -- classification
  risk_level         VARCHAR(20)  NOT NULL DEFAULT 'low',
  data_sensitivity   VARCHAR(30)  NOT NULL DEFAULT 'internal',

  -- details
  reason             TEXT,
  error_code         VARCHAR(100),
  error_class        VARCHAR(255),
  error_message_short VARCHAR(500),

  -- LLM fields
  provider           VARCHAR(50),
  model              VARCHAR(100),
  tokens_in          INTEGER,
  tokens_out         INTEGER,
  cost_usd           NUMERIC(12,6),
  latency_ms         INTEGER,

  -- tool fields
  tool_name          VARCHAR(100),
  tool_risk_level    VARCHAR(20),
  tool_args_hash     VARCHAR(64),
  egress_domain      VARCHAR(255),
  sandbox_violation  BOOLEAN,

  -- data access fields
  resource           VARCHAR(255),
  data_access_scope  VARCHAR(255),
  row_count          INTEGER,

  -- approvals
  approval_required_roles JSONB,
  approval_chain          JSONB,
  approver_id             VARCHAR(100),
  approval_request_id     VARCHAR(36),
  approval_latency_ms     INTEGER,

  -- artifacts
  artifact_ids        JSONB,
  artifact_types      JSONB,
  artifact_hashes     JSONB,
  artifact_sensitivity VARCHAR(30),

  -- tamper-evident audit
  prev_event_hash    VARCHAR(64),
  event_hash         VARCHAR(64),
  prompt_hash        VARCHAR(64),

  -- idempotency
  idempotency_key    VARCHAR(255) UNIQUE,

  -- timestamps
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Query performance indexes
CREATE INDEX IF NOT EXISTS idx_audit_trace_time    ON audit_events(trace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_type_time     ON audit_events(event_type, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_agent_time    ON audit_events(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_dept_time     ON audit_events(department, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_decision_time ON audit_events(decision, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_approval_req  ON audit_events(event_type) WHERE event_type LIKE 'approval_%';
CREATE INDEX IF NOT EXISTS idx_audit_errors        ON audit_events(error_code, created_at) WHERE error_code IS NOT NULL;


-- ═══════════════════════════════════════════════════════════════
--  TRACE INDEX (1 row per trace, for fast dashboard queries)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS trace_index (
  trace_id              VARCHAR(36) PRIMARY KEY,

  department            VARCHAR(50)  NOT NULL,
  requester_id          VARCHAR(100),
  environment           VARCHAR(20)  NOT NULL DEFAULT 'prod',

  -- lifecycle
  started_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
  ended_at              TIMESTAMPTZ,
  last_event_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
  status                VARCHAR(50)  NOT NULL DEFAULT 'running',
  current_step          VARCHAR(255),
  current_agent_id      VARCHAR(255),
  last_event_type       VARCHAR(100),
  last_error_code       VARCHAR(100),
  last_error_message_short VARCHAR(500),

  -- rollup metrics
  risk_level            VARCHAR(20)  NOT NULL DEFAULT 'low',
  data_sensitivity      VARCHAR(30)  NOT NULL DEFAULT 'internal',
  total_cost_usd        NUMERIC(12,6) NOT NULL DEFAULT 0,
  total_tokens_in       INTEGER NOT NULL DEFAULT 0,
  total_tokens_out      INTEGER NOT NULL DEFAULT 0,
  tool_calls            INTEGER NOT NULL DEFAULT 0,
  denied_calls          INTEGER NOT NULL DEFAULT 0,
  approval_pending      BOOLEAN NOT NULL DEFAULT FALSE,

  -- integrity
  audit_chain_ok        BOOLEAN,
  audit_chain_checked_at TIMESTAMPTZ,

  -- search
  summary               TEXT
);

CREATE INDEX IF NOT EXISTS idx_trace_last_event ON trace_index(last_event_at DESC);
CREATE INDEX IF NOT EXISTS idx_trace_status     ON trace_index(status);
CREATE INDEX IF NOT EXISTS idx_trace_dept_time  ON trace_index(department, last_event_at DESC);
CREATE INDEX IF NOT EXISTS idx_trace_risk       ON trace_index(risk_level);
CREATE INDEX IF NOT EXISTS idx_trace_approval   ON trace_index(approval_pending) WHERE approval_pending = TRUE;


-- ═══════════════════════════════════════════════════════════════
--  METRICS ROLLUPS HOURLY (aggregated for admin dashboard)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS metrics_rollups_hourly (
  bucket_start           TIMESTAMPTZ  NOT NULL,
  department             VARCHAR(50)  NOT NULL,
  agent_id               VARCHAR(255) NOT NULL DEFAULT '*',
  metric_scope           VARCHAR(20)  NOT NULL DEFAULT 'dept',

  traces_started         INTEGER NOT NULL DEFAULT 0,
  traces_completed       INTEGER NOT NULL DEFAULT 0,
  traces_failed          INTEGER NOT NULL DEFAULT 0,
  traces_needs_approval  INTEGER NOT NULL DEFAULT 0,

  tool_calls             INTEGER NOT NULL DEFAULT 0,
  tool_denied            INTEGER NOT NULL DEFAULT 0,
  tool_failed            INTEGER NOT NULL DEFAULT 0,

  llm_calls              INTEGER NOT NULL DEFAULT 0,
  llm_failed             INTEGER NOT NULL DEFAULT 0,
  tokens_in              BIGINT  NOT NULL DEFAULT 0,
  tokens_out             BIGINT  NOT NULL DEFAULT 0,
  cost_usd               NUMERIC(14,6) NOT NULL DEFAULT 0,

  approval_requests      INTEGER NOT NULL DEFAULT 0,
  approvals_granted      INTEGER NOT NULL DEFAULT 0,
  approvals_denied       INTEGER NOT NULL DEFAULT 0,
  approval_latency_ms_p50 INTEGER,
  approval_latency_ms_p95 INTEGER,

  execution_time_ms_p50  INTEGER,
  execution_time_ms_p95  INTEGER,

  PRIMARY KEY(bucket_start, department, agent_id, metric_scope)
);

CREATE INDEX IF NOT EXISTS idx_rollups_hourly_dept_time
  ON metrics_rollups_hourly(department, bucket_start DESC);


-- ═══════════════════════════════════════════════════════════════
--  DONE
-- ═══════════════════════════════════════════════════════════════

DO $$
BEGIN
    RAISE NOTICE 'Database initialized: pgvector enabled, 8 schemas + 3 dashboard tables created';
END $$;
