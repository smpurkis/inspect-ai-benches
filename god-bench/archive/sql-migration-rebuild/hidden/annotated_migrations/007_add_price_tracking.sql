-- Migration 007: Add product price-change audit trail
--
-- Creates a history table so every price change is recorded.
-- The trigger should fire AFTER a price column UPDATE, only when the
-- price actually changes, and must log the PREVIOUS price as old_price
-- and the NEW price as new_price.

CREATE TABLE product_price_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    old_price  REAL    NOT NULL,
    new_price  REAL    NOT NULL,
    changed_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- BROKEN: two bugs hidden below
--   Bug A: old_price and new_price are swapped in the VALUES list
--   Bug B: trigger fires even when price did not change (missing WHEN guard)
CREATE TRIGGER trg_log_price_change AFTER UPDATE OF price ON products
FOR EACH ROW
BEGIN
    INSERT INTO product_price_history (product_id, old_price, new_price)
    VALUES (NEW.id, NEW.price, OLD.price);
END;
