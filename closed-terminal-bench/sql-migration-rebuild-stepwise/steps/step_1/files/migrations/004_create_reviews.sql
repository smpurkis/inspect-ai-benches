-- Migration 004: Create reviews table
CREATE TABLE reviews (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    rating INTEGER NOT NULL CHECK(rating BETWEEN 0 AND 10),
    comment TEXT,
    reviewed_at TEXT NOT NULL DEFAULT (datetime('now'))
);
