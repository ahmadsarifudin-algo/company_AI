-- ============================================
-- Multi-Agentic AI Enterprise OS
-- Database Initialization Script
-- ============================================
-- This runs automatically on first PostgreSQL start

-- Enable pgvector extension
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

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'Database initialized: pgvector enabled, 8 department schemas created';
END $$;
