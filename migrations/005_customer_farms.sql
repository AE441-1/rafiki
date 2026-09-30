-- Stores multiple farms owned by one customer.
-- Safe to run on databases that already contain the core schema.
CREATE TABLE IF NOT EXISTS farms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    farm_name VARCHAR(150) NOT NULL,
    region VARCHAR(100) NOT NULL,
    district VARCHAR(100) NOT NULL,
    ward VARCHAR(100) NOT NULL,
    crop_type VARCHAR(100),
    farm_size DECIMAL(10,2) DEFAULT 0,
    latitude DECIMAL(10,7),
    longitude DECIMAL(11,7),
    location_address VARCHAR(500),
    status ENUM('active', 'archived') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_farms_user (user_id),
    INDEX idx_farms_status (status)
);

-- Allows a risk result to be associated with a particular farm later,
-- while preserving older customer-level assessments.
SET @column_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'risk_assessments'
      AND COLUMN_NAME = 'farm_id'
);
SET @migration_sql = IF(
    @column_exists = 0,
    'ALTER TABLE risk_assessments ADD COLUMN farm_id INT NULL AFTER customer_id',
    'SELECT ''farm_id already exists'' AS migration_status'
);
PREPARE migration_statement FROM @migration_sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @index_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'risk_assessments'
      AND INDEX_NAME = 'idx_risk_assessments_farm'
);
SET @index_sql = IF(
    @index_exists = 0,
    'ALTER TABLE risk_assessments ADD INDEX idx_risk_assessments_farm (farm_id)',
    'SELECT ''farm risk index already exists'' AS migration_status'
);
PREPARE index_statement FROM @index_sql;
EXECUTE index_statement;
DEALLOCATE PREPARE index_statement;
