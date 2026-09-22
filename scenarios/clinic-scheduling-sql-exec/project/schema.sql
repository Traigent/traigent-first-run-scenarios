CREATE TABLE patients (
    id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    date_of_birth TEXT NOT NULL,
    city TEXT NOT NULL,
    insurance_plan TEXT NOT NULL,
    registered_on TEXT NOT NULL
);

CREATE TABLE providers (
    id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    hired_on TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE rooms (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    floor INTEGER NOT NULL,
    room_type TEXT NOT NULL
);

CREATE TABLE procedures (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    base_fee REAL NOT NULL,
    room_type TEXT NOT NULL
);

CREATE TABLE appointments (
    id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    provider_id INTEGER NOT NULL REFERENCES providers(id),
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    procedure_id INTEGER NOT NULL REFERENCES procedures(id),
    scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL,
    copay REAL NOT NULL,
    booked_on TEXT NOT NULL,
    booked_via TEXT NOT NULL
);
