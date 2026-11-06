-- =====================================================
-- CampusConnect - full database setup
-- Safe to run again: it only creates what is missing.
-- (If your tables already exist, you can instead just run
--  "python db_setup.py", which adds only the new parts.)
-- =====================================================

CREATE DATABASE IF NOT EXISTS campusconnect;

USE campusconnect;

-- 1. Events table
CREATE TABLE IF NOT EXISTS events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    category VARCHAR(100),
    description TEXT,
    event_date DATE,
    event_time VARCHAR(50),
    venue VARCHAR(200),
    organizer VARCHAR(150),
    eligibility VARCHAR(200),
    registration_link VARCHAR(500),
    expires_on DATE NULL,
    organization_admin_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Academic notices table
CREATE TABLE IF NOT EXISTS academic_notices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    category VARCHAR(100),
    description TEXT,
    notice_date DATE,
    file_path VARCHAR(500),
    expires_on DATE NULL,
    organization_admin_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Announcements table
CREATE TABLE IF NOT EXISTS announcements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    category VARCHAR(100),
    description TEXT,
    announcement_date DATE,
    expires_on DATE NULL,
    organization_admin_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Students
CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    usn VARCHAR(30) NOT NULL UNIQUE,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Organization admins (status: pending / approved / rejected)
CREATE TABLE IF NOT EXISTS organization_admins (
    id INT AUTO_INCREMENT PRIMARY KEY,
    organization_name VARCHAR(150) NOT NULL,
    organization_type VARCHAR(100) NOT NULL,
    contact_person VARCHAR(150) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Event registrations (status: registered / attended / cancelled)
--    One student can register only once per event (unique key).
CREATE TABLE IF NOT EXISTS event_registrations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_id INT NOT NULL,
    student_id INT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'registered',
    qr_token VARCHAR(64) NOT NULL,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cancelled_at DATETIME NULL,
    attended_at DATETIME NULL,
    verified_by VARCHAR(150) NULL,
    UNIQUE KEY uq_event_student (event_id, student_id),
    UNIQUE KEY uq_qr_token (qr_token),
    KEY idx_reg_student (student_id)
);

-- 7. Bookmarked events
CREATE TABLE IF NOT EXISTS event_bookmarks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    event_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_student_event (student_id, event_id)
);

-- 8. Notifications
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    notif_type VARCHAR(30) NOT NULL,
    title VARCHAR(200) NOT NULL,
    message VARCHAR(500),
    link VARCHAR(300),
    is_read TINYINT(1) NOT NULL DEFAULT 0,
    dedupe_key VARCHAR(100) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_notif_dedupe (student_id, dedupe_key),
    KEY idx_notif_student (student_id, is_read)
);

SHOW TABLES;
