-- Schema SQLite anterior ao cliente mobile, sem dados reais.

CREATE TABLE users (
	id INTEGER NOT NULL, 
	username VARCHAR(80) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	is_admin BOOLEAN NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_users_id ON users (id);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE TABLE machines (
	id INTEGER NOT NULL, 
	machine_name VARCHAR(120) NOT NULL, 
	room_name VARCHAR(120) NOT NULL, 
	room_status VARCHAR(16) NOT NULL, 
	ip VARCHAR(64) NOT NULL, 
	username VARCHAR(120) NOT NULL, 
	profile VARCHAR(1) NOT NULL, 
	inspected BOOLEAN NOT NULL, 
	last_inspection_date DATE, 
	checkup_done BOOLEAN NOT NULL, 
	last_checkup_date DATE, 
	maintenance_description TEXT, 
	os_name VARCHAR(120), 
	gpu_type VARCHAR(32), 
	ram_gb INTEGER, 
	ram_modules INTEGER, 
	cpu_model VARCHAR(120), 
	storage_type VARCHAR(16), 
	storage_gb INTEGER, 
	office_installed BOOLEAN, 
	office_version VARCHAR(60), 
	kaspersky_installed BOOLEAN, 
	kaspersky_updated BOOLEAN, 
	usb_ports_qty INTEGER, 
	usb_ports_working BOOLEAN, 
	adapters TEXT, 
	hoptodesk_id VARCHAR(64), 
	hoptodesk_password VARCHAR(128), 
	mac_address VARCHAR(32), 
	projector_lamp_hours INTEGER, 
	created_by VARCHAR(80), 
	created_at DATETIME NOT NULL, 
	updated_by VARCHAR(80), 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_machines_id ON machines (id);

CREATE TABLE machine_audits (
	id INTEGER NOT NULL, 
	machine_id INTEGER NOT NULL, 
	action VARCHAR(16) NOT NULL, 
	username VARCHAR(80) NOT NULL, 
	at DATETIME NOT NULL, 
	note TEXT, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_machine_audits_machine_id ON machine_audits (machine_id);

CREATE INDEX ix_machine_audits_id ON machine_audits (id);

CREATE TABLE push_subscriptions (
	id INTEGER NOT NULL, 
	endpoint VARCHAR(512) NOT NULL, 
	subscription_json TEXT NOT NULL, 
	user_agent VARCHAR(255), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (endpoint)
);

CREATE TABLE machine_peripherals (
	id INTEGER NOT NULL, 
	machine_id INTEGER NOT NULL, 
	peripheral_code VARCHAR(64) NOT NULL, 
	present BOOLEAN NOT NULL, 
	tested_working BOOLEAN NOT NULL, 
	quantity INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_machine_peripheral UNIQUE (machine_id, peripheral_code), 
	FOREIGN KEY(machine_id) REFERENCES machines (id) ON DELETE CASCADE
);

CREATE INDEX ix_machine_peripherals_machine_id ON machine_peripherals (machine_id);

CREATE INDEX ix_machine_peripherals_id ON machine_peripherals (id);

CREATE TABLE tickets (
	id INTEGER NOT NULL, 
	machine_id INTEGER, 
	pc_name VARCHAR(120) NOT NULL, 
	reported_user VARCHAR(120), 
	problem TEXT NOT NULL, 
	diagnostics_json TEXT, 
	status VARCHAR(16) NOT NULL, 
	created_at DATETIME NOT NULL, 
	assigned_at DATETIME, 
	assigned_by VARCHAR(80), 
	closed_at DATETIME, 
	closed_by VARCHAR(80), 
	PRIMARY KEY (id), 
	FOREIGN KEY(machine_id) REFERENCES machines (id) ON DELETE SET NULL
);

CREATE INDEX ix_tickets_machine_id ON tickets (machine_id);

CREATE INDEX ix_tickets_id ON tickets (id);

CREATE INDEX ix_tickets_pc_name ON tickets (pc_name);

CREATE TABLE machine_heartbeats (
	id INTEGER NOT NULL, 
	pc_name VARCHAR(120) NOT NULL, 
	machine_id INTEGER, 
	last_seen DATETIME NOT NULL, 
	last_user VARCHAR(120), 
	diagnostics_json TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_heartbeat_pc_name UNIQUE (pc_name), 
	FOREIGN KEY(machine_id) REFERENCES machines (id) ON DELETE SET NULL
);

CREATE INDEX ix_machine_heartbeats_pc_name ON machine_heartbeats (pc_name);

CREATE INDEX ix_machine_heartbeats_machine_id ON machine_heartbeats (machine_id);

CREATE INDEX ix_machine_heartbeats_id ON machine_heartbeats (id);
