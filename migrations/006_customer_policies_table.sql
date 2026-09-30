-- Creates the customer insurance application table for databases that only
-- contain insurance_products and were initialized before policy applications.
CREATE TABLE IF NOT EXISTS customer_policies (
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
    ) NOT NULL DEFAULT 'pending',
    FOREIGN KEY (customer_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (policy_id) REFERENCES insurance_products(id) ON DELETE CASCADE,
    FOREIGN KEY (loan_id) REFERENCES loans(id) ON DELETE SET NULL,
    INDEX idx_customer_policies_customer (customer_id),
    INDEX idx_customer_policies_status (status)
);
