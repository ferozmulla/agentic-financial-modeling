-- 002_audit_immutability_trigger.sql
-- Enforces NFR-05: 100% Append-Only Immutability on audit_events in AlloyDB / PostgreSQL

CREATE OR REPLACE FUNCTION prevent_audit_events_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'NFR-05 Governance Violation: audit_events table is strictly append-only. % operations are prohibited.', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_audit_events_row_mutation ON audit_events;
CREATE TRIGGER trg_prevent_audit_events_row_mutation
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW
EXECUTE FUNCTION prevent_audit_events_mutation();

DROP TRIGGER IF EXISTS trg_prevent_audit_events_truncate ON audit_events;
CREATE TRIGGER trg_prevent_audit_events_truncate
BEFORE TRUNCATE ON audit_events
FOR EACH STATEMENT
EXECUTE FUNCTION prevent_audit_events_mutation();
