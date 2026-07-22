PRAGMA foreign_keys = ON;

-- =====================================================
-- USERS
-- =====================================================
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fullname TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE,
    email TEXT UNIQUE,
    password TEXT NOT NULL,
    phone TEXT,
    role TEXT NOT NULL CHECK(role IN ('ADMIN','AGENT','RESPONSABLE')),
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK(status IN ('ACTIVE','INACTIVE')),
    photo TEXT DEFAULT 'default_avatar.png',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- PASSWORD RESETS
-- =====================================================
CREATE TABLE IF NOT EXISTS password_resets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    code TEXT NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- ZONES
-- =====================================================
CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK(status IN ('ACTIVE','INACTIVE')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- PARKING TYPES
-- =====================================================
CREATE TABLE IF NOT EXISTS parking_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    duration_limit INTEGER,
    price_24h REAL NOT NULL DEFAULT 0,
    extra_hour_price REAL NOT NULL DEFAULT 0,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- PARKING PLACES
-- =====================================================
CREATE TABLE IF NOT EXISTS parking_places (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id INTEGER NOT NULL,
    parking_type_id INTEGER NOT NULL,
    place_number TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'FREE'
        CHECK(status IN ('FREE','OCCUPIED','MAINTENANCE','RESERVED')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(zone_id)
        REFERENCES zones(id)
        ON DELETE CASCADE,

    FOREIGN KEY(parking_type_id)
        REFERENCES parking_types(id),

    UNIQUE(zone_id, place_number)
);

-- =====================================================
-- BRANDS
-- =====================================================
CREATE TABLE IF NOT EXISTS brands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- =====================================================
-- VEHICLE TYPES
-- =====================================================
CREATE TABLE IF NOT EXISTS vehicle_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- =====================================================
-- COLORS
-- =====================================================
CREATE TABLE IF NOT EXISTS colors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

-- =====================================================
-- VEHICLES
-- =====================================================
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    matricule TEXT NOT NULL UNIQUE,

    brand_id INTEGER,

    vehicle_type_id INTEGER,

    color_id INTEGER,

    owner_name TEXT,

    phone TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(brand_id)
        REFERENCES brands(id),

    FOREIGN KEY(vehicle_type_id)
        REFERENCES vehicle_types(id),

    FOREIGN KEY(color_id)
        REFERENCES colors(id)
);

-- =====================================================
-- PARKING SESSIONS
-- =====================================================
CREATE TABLE IF NOT EXISTS parking_sessions (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    vehicle_id INTEGER NOT NULL,

    place_id INTEGER NOT NULL,

    guard_id INTEGER NOT NULL,

    entry_datetime DATETIME NOT NULL,

    expected_exit_datetime DATETIME NOT NULL,

    exit_datetime DATETIME,

    duration_hours REAL DEFAULT 0,

    total_price REAL DEFAULT 0,

    payment_status TEXT DEFAULT 'NON_PAYE'
        CHECK(payment_status IN ('PAYE','NON_PAYE')),

    status TEXT DEFAULT 'INSIDE'
        CHECK(status IN ('INSIDE','EXITED')),

    FOREIGN KEY(vehicle_id)
        REFERENCES vehicles(id),

    FOREIGN KEY(place_id)
        REFERENCES parking_places(id),

    FOREIGN KEY(guard_id)
        REFERENCES users(id)
);

-- =====================================================
-- PAYMENTS
-- =====================================================
CREATE TABLE IF NOT EXISTS payments (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    parking_session_id INTEGER NOT NULL,

    amount REAL NOT NULL,

    payment_method TEXT NOT NULL
        CHECK(payment_method IN ('CASH','CARD')),

    payment_date DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(parking_session_id)
        REFERENCES parking_sessions(id)
);-- =====================================================
-- SHIFTS (Planning des gardes)
-- =====================================================
CREATE TABLE IF NOT EXISTS shifts (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    guard_id INTEGER NOT NULL,

    shift_date DATE NOT NULL,

    start_time TIME NOT NULL,

    end_time TIME NOT NULL,

    status TEXT NOT NULL DEFAULT 'EN_SERVICE'
        CHECK(status IN ('EN_SERVICE','CONGE','ABSENT')),

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (guard_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- =====================================================
-- REPLACEMENTS (Remplacement des gardes)
-- =====================================================
CREATE TABLE IF NOT EXISTS replacements (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    absent_guard_id INTEGER NOT NULL,

    replacement_guard_id INTEGER NOT NULL,

    start_date DATE NOT NULL,

    end_date DATE NOT NULL,

    reason TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(absent_guard_id)
        REFERENCES users(id),

    FOREIGN KEY(replacement_guard_id)
        REFERENCES users(id)
);

-- =====================================================
-- PAYMENTS HISTORY
-- =====================================================
CREATE TABLE IF NOT EXISTS payment_history (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    payment_id INTEGER NOT NULL,

    action TEXT NOT NULL,

    action_date DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(payment_id)
        REFERENCES payments(id)
        ON DELETE CASCADE
);

-- =====================================================
-- NOTIFICATIONS
-- =====================================================
CREATE TABLE IF NOT EXISTS notifications (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    title TEXT NOT NULL,

    message TEXT NOT NULL,

    type TEXT DEFAULT 'INFO'
        CHECK(type IN ('INFO','WARNING','SUCCESS','ERROR')),

    is_read INTEGER DEFAULT 0,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- LOGS
-- =====================================================
CREATE TABLE IF NOT EXISTS logs (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    user_id INTEGER,

    action TEXT NOT NULL,

    details TEXT,

    ip_address TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(user_id)
        REFERENCES users(id)
);

-- =====================================================
-- SETTINGS
-- =====================================================
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT,
    airport_name TEXT,
    airport_code TEXT,
    address TEXT,
    phone TEXT,
    email TEXT,
    logo TEXT,
    currency TEXT DEFAULT 'MAD',
    stripe_publishable_key TEXT DEFAULT 'pk_test_placeholder',
    stripe_secret_key TEXT DEFAULT 'sk_test_placeholder',
    enable_stripe INTEGER DEFAULT 0
);

-- =====================================================
-- SERVICES (Prestations de service optionnelles)
-- =====================================================
CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    description TEXT,
    icon TEXT DEFAULT 'fa-concierge-bell',
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','INACTIVE'))
);

-- =====================================================
-- PARKING SERVICES (Services choisis par session)
-- =====================================================
CREATE TABLE IF NOT EXISTS parking_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parking_session_id INTEGER NOT NULL,
    service_id INTEGER NOT NULL,
    price REAL NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(parking_session_id) REFERENCES parking_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY(service_id) REFERENCES services(id)
);

-- =====================================================
-- STRIPE PAYMENTS (Suivi des paiements Stripe en ligne)
-- =====================================================
CREATE TABLE IF NOT EXISTS stripe_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parking_session_id INTEGER NOT NULL,
    payment_intent_id TEXT NOT NULL UNIQUE,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    payment_method_type TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(parking_session_id) REFERENCES parking_sessions(id) ON DELETE CASCADE
);


-- =====================================================
-- REPORTS
-- =====================================================
CREATE TABLE IF NOT EXISTS reports (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    report_name TEXT NOT NULL,

    report_type TEXT NOT NULL,

    created_by INTEGER,

    file_path TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(created_by)
        REFERENCES users(id)
);

-- =====================================================
-- INDEXES (Optimisation)
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_vehicle_matricule
ON vehicles(matricule);

CREATE INDEX IF NOT EXISTS idx_place_status
ON parking_places(status);

CREATE INDEX IF NOT EXISTS idx_session_status
ON parking_sessions(status);

CREATE INDEX IF NOT EXISTS idx_session_entry
ON parking_sessions(entry_datetime);

CREATE INDEX IF NOT EXISTS idx_logs_user
ON logs(user_id);

CREATE INDEX IF NOT EXISTS idx_notifications_read
ON notifications(is_read);