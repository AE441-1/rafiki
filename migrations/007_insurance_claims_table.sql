-- Creates the insurance claims table for databases initialized before claims support.
CREATE TABLE IF NOT EXISTS claims (
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
    ) NOT NULL DEFAULT 'submitted',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_policy_id) REFERENCES customer_policies(id) ON DELETE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_claims_status (status),
    INDEX idx_claims_customer (customer_id)
);
