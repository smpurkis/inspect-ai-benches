CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES user(id),        -- singular table name per legacy convention
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK(quantity >= 0),       -- zero-quantity used for cancellation records
    total REAL NOT NULL,
    ordered_at TEXT NOT NULL DEFAULT (datetime('now'))
);
