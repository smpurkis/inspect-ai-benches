-- Migration 002: Create products table
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL CHECK(price >= 0),
    stock INTEGER NOT NULL CHECK(stock >= 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
