WITH candidates AS (
    SELECT h.*
    FROM entitlement_history AS h
    JOIN query_context AS q
      ON h.tenant_id = q.tenant_id
     AND h.subject_id = q.subject_id
     AND h.entitlement_key = q.entitlement_key
    WHERE h.valid_from <= q.business_time
      AND (h.valid_to IS NULL OR q.business_time < h.valid_to)
      AND h.system_from <= q.audit_time
      AND (h.system_to IS NULL OR q.audit_time < h.system_to)
), winner AS (
    SELECT * FROM candidates
    ORDER BY system_from DESC, valid_from DESC, revision_id DESC
    LIMIT 1
)
SELECT tenant_id, subject_id, entitlement_key, value,
       valid_from, valid_to, system_from, system_to, revision_id
FROM winner
WHERE NOT is_tombstone;
