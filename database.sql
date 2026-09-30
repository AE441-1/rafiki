CREATE DATABASE IF NOT EXISTS rafiki_mkombozi;

USE rafiki_mkombozi;

-- =========================================
-- USERS
-- =========================================
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    phone VARCHAR(30),
    password VARCHAR(255) NOT NULL,
    role ENUM('customer', 'bank', 'insurer') NOT NULL DEFAULT 'customer',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================
-- CUSTOMER PROFILES
-- =========================================
CREATE TABLE customer_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    customer_type VARCHAR(50),
    location VARCHAR(150),
    crop_type VARCHAR(100),
    farm_size DECIMAL(10,2) DEFAULT 0,
    business_type VARCHAR(100),
    stock_value DECIMAL(15,2) DEFAULT 0,
    latitude DECIMAL(10,7),
    longitude DECIMAL(11,7),
    location_address VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- =========================================
-- CUSTOMER FARMS
-- =========================================
CREATE TABLE farms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    farm_name VARCHAR(150) NOT NULL,
    region VARCHAR(100),
    district VARCHAR(100),
    ward VARCHAR(100),
    location VARCHAR(255),
    crop_type VARCHAR(150),
    farm_size DECIMAL(10,2) DEFAULT 0,
    farm_size_unit VARCHAR(30) DEFAULT 'acres',
    business_type VARCHAR(150),
    stock_value DECIMAL(15,2) DEFAULT 0,
    latitude DECIMAL(10,7),
    longitude DECIMAL(11,7),
    location_address VARCHAR(500),
    status ENUM('active', 'inactive') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,
    INDEX idx_farms_user (user_id)
);

-- =========================================
-- RISK ASSESSMENTS
-- =========================================
CREATE TABLE risk_assessments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    farm_id INT NULL,
    drought_score DECIMAL(5,2) DEFAULT 0,
    flood_score DECIMAL(5,2) DEFAULT 0,
    rainfall_score DECIMAL(5,2) DEFAULT 0,
    pest_pressure_score DECIMAL(5,2) DEFAULT 0,
    overall_score DECIMAL(5,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (customer_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- =========================================
-- INSURANCE PRODUCTS
-- =========================================
CREATE TABLE insurance_products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(100),
    coverage TEXT,
    premium DECIMAL(15,2) DEFAULT 0,
    duration VARCHAR(50),
    status ENUM('active', 'inactive') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================
-- AI RECOMMENDATIONS
-- =========================================
CREATE TABLE recommendations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    policy_id INT NOT NULL,
    risk_score DECIMAL(5,2),
    relevance VARCHAR(20),
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (customer_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    FOREIGN KEY (policy_id)
        REFERENCES insurance_products(id)
        ON DELETE CASCADE
);

-- =========================================
-- LOAN APPLICATIONS
-- =========================================
CREATE TABLE loan_applications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    purpose VARCHAR(255),
    duration_months INT NOT NULL,
    status ENUM(
        'pending',
        'under_review',
        'approved',
        'rejected'
    ) DEFAULT 'pending',
    application_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (customer_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- =========================================
-- LOANS
-- =========================================
CREATE TABLE loans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    application_id INT NOT NULL,
    customer_id INT NOT NULL,
    bank_id INT NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    interest_rate DECIMAL(5,2) DEFAULT 0,
    duration_months INT NOT NULL,
    status ENUM(
        'active',
        'completed',
        'defaulted',
        'cancelled'
    ) DEFAULT 'active',
    disbursement_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (application_id)
        REFERENCES loan_applications(id),

    FOREIGN KEY (customer_id)
        REFERENCES users(id),

    FOREIGN KEY (bank_id)
        REFERENCES users(id)
);

-- =========================================
-- REPAYMENTS
-- =========================================
CREATE TABLE repayments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    loan_id INT NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    payment_date DATE NOT NULL,
    status ENUM(
        'paid',
        'pending',
        'late'
    ) DEFAULT 'paid',

    FOREIGN KEY (loan_id)
        REFERENCES loans(id)
        ON DELETE CASCADE
);

-- =========================================
-- CUSTOMER INSURANCE POLICIES
-- =========================================
CREATE TABLE customer_policies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    policy_id INT NOT NULL,
    loan_id INT NULL,
    start_date DATE,
    end_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM(
        'pending',
        'active',
        'expired',
        'cancelled',
        'rejected'
    ) DEFAULT 'pending',

    FOREIGN KEY (customer_id)
        REFERENCES users(id),

    FOREIGN KEY (policy_id)
        REFERENCES insurance_products(id),

    FOREIGN KEY (loan_id)
        REFERENCES loans(id)
        ON DELETE SET NULL
);

-- =========================================
-- INSURANCE CLAIMS
-- =========================================
CREATE TABLE claims (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_policy_id INT NOT NULL,
    customer_id INT NOT NULL,
    description TEXT,
    claim_amount DECIMAL(15,2),
    status ENUM(
        'submitted',
        'under_review',
        'approved',
        'rejected',
        'paid'
    ) DEFAULT 'submitted',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (customer_policy_id)
        REFERENCES customer_policies(id),

    FOREIGN KEY (customer_id)
        REFERENCES users(id)
);

-- =========================================
-- SAMPLE INSURANCE PRODUCTS
-- =========================================
INSERT INTO insurance_products
(name, category, coverage, premium, duration, status)
VALUES
(
    'Crop Protection Insurance',
    'Agriculture',
    'Protection against selected crop-related climate risks.',
    50000,
    '12 months',
    'active'
),
(
    'Flood Protection Insurance',
    'Climate',
    'Protection against eligible flood-related losses.',
    75000,
    '12 months',
    'active'
),
(
    'Business Protection Insurance',
    'Business',
    'Protection for eligible small business risks.',
    60000,
    '12 months',
    'active'
);