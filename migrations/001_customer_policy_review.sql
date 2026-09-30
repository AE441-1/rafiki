-- Run once on databases created before customer insurance applications were added.
-- Existing active, expired, and cancelled policy rows retain their statuses.
ALTER TABLE customer_policies
MODIFY status ENUM(
    'pending',
    'active',
    'expired',
    'cancelled',
    'rejected'
) NOT NULL DEFAULT 'active';

ALTER TABLE customer_policies
ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
