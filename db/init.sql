CREATE TABLE IF NOT EXISTS participants (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    participant_id VARCHAR(64) NOT NULL,
    study_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE participants
    DROP CONSTRAINT IF EXISTS participants_participant_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_participants_tenant_participant
    ON participants(tenant_id, participant_id);
CREATE INDEX IF NOT EXISTS idx_participants_tenant_study
    ON participants(tenant_id, study_id);
CREATE INDEX IF NOT EXISTS idx_participants_status ON participants(status);

CREATE TABLE IF NOT EXISTS studies (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    study_id VARCHAR(64) NOT NULL,
    name VARCHAR(256) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_studies_tenant_study ON studies(tenant_id, study_id);

CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    study_id VARCHAR(64) NOT NULL,
    task_name VARCHAR(256) NOT NULL,
    assignee VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tasks_tenant_study ON tasks(tenant_id, study_id);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    username VARCHAR(128) NOT NULL,
    role VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_tenant_username ON users(tenant_id, username);

INSERT INTO studies (tenant_id, study_id, name)
VALUES
    ('tenant-a', 'study-a', 'Cardio Telemetry Baseline'),
    ('tenant-a', 'study-b', 'Sleep Recovery Cohort'),
    ('tenant-admin', 'ops-study', 'Platform Reliability Tracking')
ON CONFLICT (tenant_id, study_id) DO NOTHING;

INSERT INTO tasks (tenant_id, study_id, task_name, assignee, status)
VALUES
    ('tenant-a', 'study-a', 'Validate participant consent forms', 'researcher', 'open'),
    ('tenant-a', 'study-a', 'Review anomaly alerts', 'clinician', 'in_progress'),
    ('tenant-a', 'study-b', 'Prepare week-2 survey batch', 'researcher', 'open')
ON CONFLICT DO NOTHING;

INSERT INTO users (tenant_id, username, role)
VALUES
    ('tenant-a', 'researcher', 'researcher'),
    ('tenant-a', 'clinician', 'clinician'),
    ('tenant-admin', 'admin', 'admin')
ON CONFLICT (tenant_id, username) DO NOTHING;
