-- The recommendation engine stores HIGH, MEDIUM, and LOW labels here.
-- Existing databases created with DECIMAL(5,2) must widen this column.
ALTER TABLE recommendations
MODIFY COLUMN relevance VARCHAR(20) NULL;
