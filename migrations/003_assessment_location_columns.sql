-- Adds fields used by the location-based assessment to older databases.
-- Safe to run more than once (existing columns are left unchanged).
SET @column_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'customer_profiles'
      AND COLUMN_NAME = 'latitude'
);
SET @migration_sql = IF(
    @column_exists = 0,
    'ALTER TABLE customer_profiles ADD COLUMN latitude DECIMAL(10,7) NULL',
    'SELECT ''latitude already exists'' AS migration_status'
);
PREPARE migration_statement FROM @migration_sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @column_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'customer_profiles'
      AND COLUMN_NAME = 'longitude'
);
SET @migration_sql = IF(
    @column_exists = 0,
    'ALTER TABLE customer_profiles ADD COLUMN longitude DECIMAL(11,7) NULL',
    'SELECT ''longitude already exists'' AS migration_status'
);
PREPARE migration_statement FROM @migration_sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @column_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'customer_profiles'
      AND COLUMN_NAME = 'location_address'
);
SET @migration_sql = IF(
    @column_exists = 0,
    'ALTER TABLE customer_profiles ADD COLUMN location_address VARCHAR(500) NULL',
    'SELECT ''location_address already exists'' AS migration_status'
);
PREPARE migration_statement FROM @migration_sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;
