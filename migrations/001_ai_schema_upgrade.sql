-- ============================================================================
-- Campus Retain 2.0 - AI Schema Upgrade Migration (PostgreSQL / Neon)
-- Migration: 001_ai_schema_upgrade.sql
-- Description: Non-destructive, idempotent schema upgrade for Phases 1-7 AI capabilities.
-- Safeguards: Never drops tables, never drops columns, preserves all existing data.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Upgrade Table: item
-- ----------------------------------------------------------------------------
ALTER TABLE item ADD COLUMN IF NOT EXISTS item_type VARCHAR(20) DEFAULT 'found';
ALTER TABLE item ADD COLUMN IF NOT EXISTS reported_by VARCHAR(120);
ALTER TABLE item ADD COLUMN IF NOT EXISTS date_lost TIMESTAMP;
ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_category VARCHAR(50);
ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_primary_color VARCHAR(30);
ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_secondary_colors JSON;
ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_brand VARCHAR(50);
ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_model VARCHAR(50);
ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_visible_text JSON;
ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_distinctive_features JSON;
ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_condition VARCHAR(30);
ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_confidence FLOAT;
ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_analysis_status VARCHAR(20) DEFAULT 'not_applicable';
ALTER TABLE item ADD COLUMN IF NOT EXISTS ai_analyzed_at TIMESTAMP;

-- Backfill existing legacy items with default 'found' type where unset
UPDATE item SET item_type = 'found' WHERE item_type IS NULL;

-- ----------------------------------------------------------------------------
-- 2. Upgrade Table: claim
-- ----------------------------------------------------------------------------
ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_confidence_score INTEGER;
ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_confidence_level VARCHAR(20);
ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_matching_factors JSON;
ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_conflicting_factors JSON;
ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_explanation TEXT;
ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_recommendation VARCHAR(50) DEFAULT 'manual_review';
ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_analysis_status VARCHAR(20) DEFAULT 'pending';
ALTER TABLE claim ADD COLUMN IF NOT EXISTS ai_analyzed_at TIMESTAMP;

-- ----------------------------------------------------------------------------
-- 3. Create Table: item_match (if not already created)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS item_match (
    id SERIAL PRIMARY KEY,
    lost_item_id INTEGER NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    found_item_id INTEGER NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    match_score INTEGER NOT NULL,
    confidence VARCHAR(20) NOT NULL,
    matching_attributes JSON,
    differences JSON,
    explanation TEXT,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 4. Create Performance Indexes (Idempotent)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_item_type ON item(item_type);
CREATE INDEX IF NOT EXISTS idx_item_status ON item(status);
CREATE INDEX IF NOT EXISTS idx_item_match_lost ON item_match(lost_item_id);
CREATE INDEX IF NOT EXISTS idx_item_match_found ON item_match(found_item_id);
CREATE INDEX IF NOT EXISTS idx_item_match_status ON item_match(status);

COMMIT;
