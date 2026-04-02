CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    parent_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- partial index covers only actively-displayed categories (those with active = 1)
CREATE INDEX idx_active_categories ON categories(name) WHERE active = 1;

INSERT INTO categories (id, name, parent_id) VALUES (1, 'Electronics', NULL);
INSERT INTO categories (id, name, parent_id) VALUES (2, 'Laptops', 1);
INSERT INTO categories (id, name, parent_id) VALUES (3, 'Phones', 1);
