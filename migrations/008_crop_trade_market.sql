-- Persistent crop listings and cross-border trade tracking.
CREATE TABLE IF NOT EXISTS crop_listings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    farmer_id INT NOT NULL,
    crop_name VARCHAR(100) NOT NULL,
    quantity_available DECIMAL(12,3) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    price_per_unit DECIMAL(15,2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'TZS',
    origin_country VARCHAR(80) NOT NULL DEFAULT 'Tanzania',
    origin_location VARCHAR(160) NOT NULL,
    market_scope ENUM('tanzania', 'africa') NOT NULL DEFAULT 'tanzania',
    status ENUM('available', 'sold_out', 'withdrawn') NOT NULL DEFAULT 'available',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_crop_listings_farmer
        FOREIGN KEY (farmer_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_crop_listings_status_scope (status, market_scope),
    INDEX idx_crop_listings_farmer (farmer_id),
    INDEX idx_crop_listings_crop (crop_name)
);

-- A percentage-rate field lets shipment insurance be priced in the trade currency.
SET @column_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'insurance_products'
      AND COLUMN_NAME = 'premium_rate_percent'
);
SET @migration_sql = IF(
    @column_exists = 0,
    'ALTER TABLE insurance_products ADD COLUMN premium_rate_percent DECIMAL(5,2) NULL AFTER premium',
    'SELECT ''premium_rate_percent already exists'' AS migration_status'
);
PREPARE migration_statement FROM @migration_sql;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

INSERT INTO insurance_products
    (name, category, coverage, premium, premium_rate_percent, duration, status)
SELECT
    'Agricultural Trade Protection',
    'Agricultural Trade Insurance',
    'Optional shipment cover for eligible crop loss or damage while a trade is in transit. Coverage terms and claims are subject to insurer review.',
    0,
    2.50,
    'Per trade',
    'active'
WHERE NOT EXISTS (
    SELECT 1
    FROM insurance_products
    WHERE name = 'Agricultural Trade Protection'
      AND category = 'Agricultural Trade Insurance'
);

CREATE TABLE IF NOT EXISTS crop_trades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    listing_id INT NOT NULL,
    seller_id INT NOT NULL,
    buyer_id INT NOT NULL,
    quantity DECIMAL(12,3) NOT NULL,
    unit_price DECIMAL(15,2) NOT NULL,
    currency CHAR(3) NOT NULL,
    destination_country VARCHAR(80) NOT NULL,
    destination_location VARCHAR(160) NOT NULL,
    status ENUM(
        'requested',
        'accepted',
        'rejected',
        'in_transit',
        'delivered',
        'completed',
        'cancelled'
    ) NOT NULL DEFAULT 'requested',
    insurance_product_id INT NULL,
    insurance_premium DECIMAL(15,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_crop_trades_listing
        FOREIGN KEY (listing_id) REFERENCES crop_listings(id) ON DELETE CASCADE,
    CONSTRAINT fk_crop_trades_seller
        FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_crop_trades_buyer
        FOREIGN KEY (buyer_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_crop_trades_insurance
        FOREIGN KEY (insurance_product_id) REFERENCES insurance_products(id) ON DELETE SET NULL,
    INDEX idx_crop_trades_seller_status (seller_id, status),
    INDEX idx_crop_trades_buyer_status (buyer_id, status),
    INDEX idx_crop_trades_listing (listing_id)
);
