-- AU-hartland — the columns the extension adds to base tables (D-82, D-83, and the customer mail address). Kept by a
-- reset, only emptied; the model maps them.
--
-- This runs first in a build, and it ALSO runs on a world that is already built at the same as_of
-- (run-automation.sh), so a column added here later reaches every built world without a reset. Every statement must
-- therefore be idempotent and need no other step: a generated column (like c_email) arrives complete, while a column
-- that a later step fills (c_center_sk by 24-centers, d_working_day by 25-calendar) would arrive empty on a built
-- world, and needs a reset + rebuild instead.
ALTER TABLE customer ADD COLUMN IF NOT EXISTS c_center_sk integer;      -- 24-centers.sql
ALTER TABLE date_dim ADD COLUMN IF NOT EXISTS d_working_day boolean;    -- 25-calendar.sql
-- The customer's mail address, which the customer mail actions (notify_customer, emit) send to. It is generated from
-- the key under the reserved .example domain (RFC 2606), so a demo mail can never reach a real inbox. TPC-DS's own
-- c_email_address is not used: its random domains include registered ones, and some rows are NULL or duplicates.
-- A reset keeps it as it is, because it holds no build state.
ALTER TABLE customer ADD COLUMN IF NOT EXISTS c_email varchar(64)
  GENERATED ALWAYS AS ('customer-' || c_customer_sk || '@customers.hartland.example') STORED;
