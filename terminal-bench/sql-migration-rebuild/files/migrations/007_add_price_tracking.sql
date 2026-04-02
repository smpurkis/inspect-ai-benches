CREATE TABLE product_price_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    old_price  REAL    NOT NULL,
    new_price  REAL    NOT NULL,
    changed_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- trigger records every price column touch for compliance auditing
CREATE TRIGGER trg_log_price_change AFTER UPDATE OF price ON products
FOR EACH ROW
BEGIN
    INSERT INTO product_price_history (product_id, old_price, new_price)
    VALUES (NEW.id, NEW.price, OLD.price);
END;
