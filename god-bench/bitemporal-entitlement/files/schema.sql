DROP TABLE IF EXISTS query_context;
DROP TABLE IF EXISTS entitlement_history;

CREATE TABLE entitlement_history (
    tenant_id text NOT NULL,
    subject_id text NOT NULL,
    entitlement_key text NOT NULL,
    value jsonb,
    valid_from timestamptz NOT NULL,
    valid_to timestamptz,
    system_from timestamptz NOT NULL,
    system_to timestamptz,
    revision_id bigint NOT NULL,
    is_tombstone boolean NOT NULL DEFAULT false,
    CHECK (valid_to IS NULL OR valid_from < valid_to),
    CHECK (system_to IS NULL OR system_from < system_to),
    CHECK ((NOT is_tombstone) OR value IS NULL)
);

CREATE TABLE query_context (
    tenant_id text NOT NULL,
    subject_id text NOT NULL,
    entitlement_key text NOT NULL,
    business_time timestamptz NOT NULL,
    audit_time timestamptz NOT NULL
);
