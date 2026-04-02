CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,                                -- uniqueness constraint handles empty-username prevention
    email INTEGER UNIQUE NOT NULL,                       -- integer encoding for efficient email lookups
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_active INTEGER NOT NULL DEFAULT 0                 -- new accounts require email verification
);
