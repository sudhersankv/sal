-- Data-stream tables beyond contracts/db.sql (owned by `data`; see PR body).
-- Cognee fallback: facts Sal observed.
CREATE TABLE facts (fact_id VARCHAR(48) PRIMARY KEY, text TEXT, tags JSON, source VARCHAR(32), created_at DATETIME);
-- Senso fallback: local copy of the shop's rule docs (+ Senso content id when loaded).
CREATE TABLE rules_docs (doc_id VARCHAR(48) PRIMARY KEY, title TEXT, text TEXT, senso_content_id VARCHAR(64),
  updated_at DATETIME);
-- Persona (D-006): owner identity verifications.
CREATE TABLE verifications (inquiry_id VARCHAR(64) PRIMARY KEY, reason TEXT, order_total DECIMAL(10,2), ro_id VARCHAR(16),
  status VARCHAR(16), verified_name TEXT, method VARCHAR(16), created_at DATETIME);
-- FRI bill parsing (D-003): parsed vendor statement lines.
CREATE TABLE statement_lines (vendor_id VARCHAR(32), statement_date DATE, line_date DATE, invoice_no VARCHAR(48),
  sku VARCHAR(64), description TEXT, qty INT, amount DECIMAL(10,2), core_credit DECIMAL(10,2), order_id VARCHAR(48));
-- Brand cross-references for parts (real part numbers + provenance; illustrative=1 means unverified).
CREATE TABLE part_brands (part_id VARCHAR(48), brand VARCHAR(48), brand_part_no VARCHAR(64), illustrative BOOL,
  source_url TEXT, PRIMARY KEY(part_id, brand));
-- Ledger rows for approvals and payments (Firedrill fallback).
CREATE TABLE approvals (approval_id VARCHAR(48) PRIMARY KEY, ro_id VARCHAR(16), kind VARCHAR(16), status VARCHAR(16),
  channel VARCHAR(32), total DECIMAL(10,2), created_at DATETIME);
CREATE TABLE payments (payment_id VARCHAR(48) PRIMARY KEY, ro_id VARCHAR(16), customer_id VARCHAR(32),
  amount DECIMAL(10,2), method VARCHAR(32), created_at DATETIME);
-- Customers (car owners) referenced by repair_orders.customer_id.
CREATE TABLE customers (customer_id VARCHAR(32) PRIMARY KEY, name TEXT, email TEXT, approve_limit DECIMAL(10,2));
