CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT,                                           -- allow NULL for draft products pending review
    category TEXT NOT NULL,
    price REAL NOT NULL CHECK(price >= 0),               -- zero allowed for promotional giveaways
    stock INTEGER NOT NULL CHECK(stock >= 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
