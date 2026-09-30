-- Adds the climate-based crop pest-pressure estimate to older databases.
-- Safe to run more than once (an existing column is left unchanged).
SET @column_exists = (
	SELECT COUNT(*)
	FROM INFORMATION_SCHEMA.COLUMNS
	WHERE TABLE_SCHEMA = DATABASE()
	  AND TABLE_NAME = 'risk_assessments'
	  AND COLUMN_NAME = 'pest_pressure_score'
);
SET @migration_sql = IF(
	@column_exists = 0,
	'ALTER TABLE risk_assessments ADD COLUMN pest_pressure_score DECIMAL(5,2) DEFAULT 0 AFTER rainfall_score',
	'SELECT ''pest_pressure_score already exists'' AS migration_status'
);
PREPARE migration_statement FROM @migration_sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;
