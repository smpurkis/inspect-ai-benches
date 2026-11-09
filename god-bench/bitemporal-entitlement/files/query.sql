-- BUGGY STARTER: it ignores audit-time corrections, tombstones, and tie rules.
SELECT DISTINCT ON (h.tenant_id, h.subject_id, h.entitlement_key)
       h.tenant_id, h.subject_id, h.entitlement_key, h.value,
       h.valid_from, h.valid_to, h.system_from, h.system_to, h.revision_id
FROM entitlement_history AS h
JOIN query_context AS q
  ON h.tenant_id = q.tenant_id
 AND h.subject_id = q.subject_id
 AND h.entitlement_key = q.entitlement_key
WHERE h.valid_from <= q.business_time
  AND (h.valid_to IS NULL OR q.business_time <= h.valid_to)
ORDER BY h.tenant_id, h.subject_id, h.entitlement_key, h.valid_from DESC;
