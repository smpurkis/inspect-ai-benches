-- Migration 006: Create categories table with self-referential FK
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    parent_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- BROKEN: the partial index WHERE clause is invalid
CREATE INDEX idx_active_categories ON categories(name) WHERE active = 1;

-- Seed data: root category and two children
INSERT INTO categories (id, name, parent_id) VALUES (1, 'Electronics', NULL);
INSERT INTO categories (id, name, parent_id) VALUES (2, 'Laptops', 1);
INSERT INTO categories (id, name, parent_id) VALUES (3, 'Phones', 1);
