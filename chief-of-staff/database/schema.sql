CREATE TABLE responsibilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    owner TEXT,
    priority TEXT DEFAULT 'Medium',
    status TEXT DEFAULT 'Active',
    due_date TEXT,
    verification_status TEXT DEFAULT 'Pending',
    communication_complete INTEGER DEFAULT 0,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE waiting_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    contact TEXT,
    organization TEXT,
    waiting_since TEXT,
    next_follow_up TEXT,
    status TEXT DEFAULT 'Waiting',
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE daily_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    note TEXT,
    discovery TEXT,
    lesson TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
