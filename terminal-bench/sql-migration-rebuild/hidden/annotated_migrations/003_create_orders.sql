-- Migration 003: Create orders table
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES user(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    total REAL NOT NULL,
    ordered_at TEXT NOT NULL DEFAULT (datetime('now'))
);
