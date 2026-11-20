-- Sal SingleStore DDL (SPEC §7.3). Lead-owned. VECTOR dim confirmed by data (D5).
CREATE TABLE vendors (vendor_id VARCHAR(32) PRIMARY KEY, name TEXT, kind ENUM('counter','online'),
  cutoff_local TIME, free_ship_threshold DECIMAL(10,2), account_terms TEXT);
CREATE TABLE parts (part_id VARCHAR(48) PRIMARY KEY, oem_part_no VARCHAR(64), part_type VARCHAR(48),
  position VARCHAR(32), description TEXT, has_core BOOL, core_charge DECIMAL(10,2), source_url TEXT);
CREATE TABLE fitments (part_id VARCHAR(48), year INT, make VARCHAR(32), model VARCHAR(48),
  engine_l DECIMAL(3,1), dtc VARCHAR(8), notes TEXT, KEY(make, model, year));
CREATE TABLE vendor_catalog (vendor_id VARCHAR(32), sku VARCHAR(64), vendor_part_no VARCHAR(64),
  oem_part_no VARCHAR(64), brand VARCHAR(48), description TEXT, price DECIMAL(10,2),
  qty_on_hand INT, eta_minutes INT, shopify_variant_id VARCHAR(64), embedding VECTOR(1024),
  PRIMARY KEY(vendor_id, sku));
CREATE TABLE inventory (sku VARCHAR(64) PRIMARY KEY, name TEXT, part_type VARCHAR(48), qty INT, min_qty INT, max_qty INT);
CREATE TABLE bookings (booking_id VARCHAR(32) PRIMARY KEY, date DATE, service_code VARCHAR(32),
  vehicle TEXT, parts_needed JSON);
CREATE TABLE repair_orders (ro_id VARCHAR(16) PRIMARY KEY, opened_at DATETIME, vin VARCHAR(17),
  dtc VARCHAR(8), complaint TEXT, bay INT, customer_id VARCHAR(32), status VARCHAR(16));
CREATE TABLE orders (order_id VARCHAR(48) PRIMARY KEY, vendor_id VARCHAR(32), ro_id VARCHAR(16), placed_at DATETIME,
  promised_at DATETIME, delivered_at DATETIME, total DECIMAL(10,2), channel VARCHAR(16), external_ref TEXT, run_id VARCHAR(48));
CREATE TABLE order_lines (order_id VARCHAR(48), sku VARCHAR(64), brand VARCHAR(48), part_type VARCHAR(48),
  qty INT, unit_price DECIMAL(10,2), core_charge DECIMAL(10,2));
CREATE TABLE purchase_history (order_id VARCHAR(48), vendor_id VARCHAR(32), brand VARCHAR(48), part_type VARCHAR(48),
  placed_at DATETIME, promised_at DATETIME, delivered_at DATETIME, unit_price DECIMAL(10,2),
  comeback BOOL, core_credit_due DECIMAL(10,2), core_credit_received DECIMAL(10,2));
CREATE TABLE rules (rule_id VARCHAR(32) PRIMARY KEY, title TEXT, rule_text TEXT, status VARCHAR(16),
  evidence JSON, senso_content_id VARCHAR(64), created_at DATETIME);
CREATE TABLE metrics (run_id VARCHAR(48), day VARCHAR(3), variant VARCHAR(32), name VARCHAR(48), value DOUBLE);
