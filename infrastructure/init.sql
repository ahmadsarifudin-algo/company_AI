-- ============================================
-- Multi-Agentic AI Enterprise OS
-- Database Initialization Script (COMPLETE)
-- ============================================
-- This runs automatically on first PostgreSQL start.
-- It creates ALL tables, indexes, and seeds initial data.

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

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
--  USERS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS users (
  id                    VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
  email                 VARCHAR(255) NOT NULL UNIQUE,
  name                  VARCHAR(255) NOT NULL,
  hashed_password       VARCHAR(255),
  department            VARCHAR(50)  NOT NULL,
  role                  VARCHAR(50)  NOT NULL DEFAULT 'contributor',  -- admin|manager|lead|contributor
  is_active             BOOLEAN      NOT NULL DEFAULT FALSE,

  -- Invite token
  invite_token_hash     VARCHAR(64),
  invite_expires_at     TIMESTAMPTZ,

  -- Communication channels
  phone_whatsapp        VARCHAR(20),
  telegram_chat_id      VARCHAR(64),
  notification_channels VARCHAR(100) NOT NULL DEFAULT 'email',

  -- SOUL personality (FK added later after user_souls table exists)
  active_soul_id        VARCHAR(36),

  -- Timestamps
  created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_email      ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_dept       ON users(department);
CREATE INDEX IF NOT EXISTS idx_users_invite     ON users(invite_token_hash) WHERE invite_token_hash IS NOT NULL;


-- ═══════════════════════════════════════════════════════════════
--  AGENTS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS agents (
  id                      VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
  name                    VARCHAR(255) NOT NULL,
  department              VARCHAR(50)  NOT NULL,
  tier                    VARCHAR(20)  NOT NULL DEFAULT 'standard',
  status                  VARCHAR(20)  NOT NULL DEFAULT 'idle',
  description             TEXT,
  system_prompt           TEXT,
  tools_config            JSONB,
  paired_user_id          VARCHAR(36)  REFERENCES users(id),

  -- Prompt override fields
  system_prompt_override  TEXT,
  prompt_version          INTEGER      NOT NULL DEFAULT 0,
  prompt_updated_at       TIMESTAMPTZ,
  prompt_updated_by       VARCHAR(100),

  -- Timestamps
  created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agents_dept ON agents(department);


-- ═══════════════════════════════════════════════════════════════
--  TASKS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS tasks (
  id                  VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
  title               VARCHAR(500) NOT NULL,
  description         TEXT,
  department          VARCHAR(50)  NOT NULL,
  status              VARCHAR(20)  NOT NULL DEFAULT 'pending',  -- pending|running|waiting_approval|completed|failed
  priority            VARCHAR(5)   NOT NULL DEFAULT 'P2',
  plan_json           JSONB,
  result_json         JSONB,
  assigned_agent_id   VARCHAR(36)  REFERENCES agents(id),
  submitted_by        VARCHAR(36)  REFERENCES users(id),

  created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tasks_dept ON tasks(department);


-- ═══════════════════════════════════════════════════════════════
--  KNOWLEDGE DOCUMENTS (RAG with pgvector)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS knowledge_documents (
  id                  VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
  title               VARCHAR(500) NOT NULL,
  content             TEXT         NOT NULL,
  department          VARCHAR(50)  NOT NULL,
  doc_type            VARCHAR(50)  NOT NULL DEFAULT 'general',  -- sop|policy|decision|report|memo|general
  source              VARCHAR(500),
  chunk_index         INTEGER      NOT NULL DEFAULT 0,
  parent_doc_id       VARCHAR(36),
  embedding           vector(1536),
  metadata_json       JSONB,

  created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_dept      ON knowledge_documents(department);
CREATE INDEX IF NOT EXISTS idx_knowledge_parent    ON knowledge_documents(parent_doc_id) WHERE parent_doc_id IS NOT NULL;


-- ═══════════════════════════════════════════════════════════════
--  PROMPT HISTORY (version control for agent prompts)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS prompt_history (
  id                  VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
  agent_id            VARCHAR(36)  NOT NULL REFERENCES agents(id),
  version             INTEGER      NOT NULL,
  prompt_text         TEXT         NOT NULL,
  changed_by          VARCHAR(100) NOT NULL,
  changed_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
  change_reason       VARCHAR(500)
);

CREATE INDEX IF NOT EXISTS idx_prompt_history_agent ON prompt_history(agent_id);


-- ═══════════════════════════════════════════════════════════════
--  NOTIFICATION LOGS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS notification_logs (
  id                  VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,

  -- Correlation
  trace_id            VARCHAR(36),
  task_id             VARCHAR(36),
  user_id             VARCHAR(36),

  -- Channel
  channel             VARCHAR(20)  NOT NULL,  -- email|whatsapp|dashboard|google_chat
  direction           VARCHAR(10)  NOT NULL DEFAULT 'outbound',  -- inbound|outbound

  -- Message
  recipient           VARCHAR(255) NOT NULL,
  subject             VARCHAR(500),
  body_preview        VARCHAR(500),
  template            VARCHAR(100),  -- approval_request|task_report|feedback|general

  -- Delivery
  status              VARCHAR(20)  NOT NULL DEFAULT 'queued',  -- queued|sent|delivered|failed|replied
  external_id         VARCHAR(255),
  error_message       TEXT,

  -- Reply tracking
  replied_at          TIMESTAMPTZ,
  reply_content       TEXT,

  -- Metrics
  retry_count         INTEGER      NOT NULL DEFAULT 0,

  created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notif_trace   ON notification_logs(trace_id) WHERE trace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_notif_user    ON notification_logs(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_notif_channel ON notification_logs(channel);


-- ═══════════════════════════════════════════════════════════════
--  INTEGRATION CREDENTIALS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS integration_credentials (
  id                  VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
  key                 VARCHAR(100) NOT NULL UNIQUE,
  value               TEXT         NOT NULL,
  service             VARCHAR(50)  NOT NULL,  -- google|twilio|smtp
  is_secret           BOOLEAN      NOT NULL DEFAULT FALSE,
  is_active           BOOLEAN      NOT NULL DEFAULT TRUE,

  created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_intcred_key     ON integration_credentials(key);
CREATE INDEX IF NOT EXISTS idx_intcred_service ON integration_credentials(service);


-- ═══════════════════════════════════════════════════════════════
--  SOUL TEMPLATES (preset personalities)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS soul_templates (
  id              VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
  name            VARCHAR(100) NOT NULL UNIQUE,
  description     VARCHAR(500),
  tone            VARCHAR(50)  NOT NULL DEFAULT 'friendly',
  language_style  VARCHAR(50)  NOT NULL DEFAULT 'auto',
  personality     TEXT         NOT NULL,
  boundaries      TEXT,
  greeting        VARCHAR(500),
  icon            VARCHAR(10),
  sort_order      INTEGER      DEFAULT 0,
  is_active       BOOLEAN      DEFAULT TRUE,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);


-- ═══════════════════════════════════════════════════════════════
--  USER SOULS (per-user custom/cloned)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS user_souls (
  id              VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
  user_id         VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name            VARCHAR(100) NOT NULL,
  tone            VARCHAR(50)  NOT NULL DEFAULT 'friendly',
  language_style  VARCHAR(50)  NOT NULL DEFAULT 'auto',
  personality     TEXT         NOT NULL,
  boundaries      TEXT,
  greeting        VARCHAR(500),
  template_id     VARCHAR(36)  REFERENCES soul_templates(id) ON DELETE SET NULL,
  is_active       BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Only one active soul per user
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_soul
  ON user_souls(user_id) WHERE is_active = TRUE;

-- Add FK from users.active_soul_id → user_souls.id
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'fk_users_active_soul' AND table_name = 'users'
  ) THEN
    ALTER TABLE users ADD CONSTRAINT fk_users_active_soul
      FOREIGN KEY (active_soul_id) REFERENCES user_souls(id) ON DELETE SET NULL;
  END IF;
END $$;


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
--  METRICS ROLLUPS HOURLY
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
--  NOTE: Seed data (admin user, agents, soul templates) is handled
--  by Python's seed.py at application startup. This ensures bcrypt
--  password hashes are generated by the same library that verifies them.
--  Run: python -m app.seed  (or auto-runs on startup in dev mode)
-- ═══════════════════════════════════════════════════════════════


DO $$
BEGIN
    RAISE NOTICE '✅ Database schema initialized:';
    RAISE NOTICE '   - pgvector + uuid-ossp + pgcrypto extensions enabled';
    RAISE NOTICE '   - 8 department schemas created';
    RAISE NOTICE '   - 12 tables created';
    RAISE NOTICE '   - Seed data will be applied by app startup (python -m app.seed)';
END $$;
