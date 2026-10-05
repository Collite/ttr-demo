-- The six tables `scripts/sql/evolution-reference.sql` reads, with the estate's own column types (kantheon
-- `packages/investment/model/entry/investment-schema-v1.sql` + `-v2.sql`, and the ledger's three `-v3.sql` columns —
-- IA-P4b·S4b.1) — only what the reference touches, so the fixture book loads into an empty PostgreSQL 16 without the
-- rest of the estate.
CREATE TABLE investment_asset_price (
    isin       CHAR(12) NOT NULL,
    price_date DATE     NOT NULL,
    price      NUMERIC(18, 6),
    currency   CHAR(3),
    PRIMARY KEY (isin, price_date)
);
CREATE TABLE investment_transaction (
    sk            BIGSERIAL PRIMARY KEY,
    external_id   TEXT NOT NULL,
    portfolio_ref TEXT,
    asset_ref     CHAR(12),
    leg           TEXT,
    operation     TEXT,
    trade_date    DATE,
    quantity      NUMERIC(18, 6),
    amount        NUMERIC(18, 2),
    currency      CHAR(3),
    reversal_of   TEXT,
    -- investment-schema-v3 (IA-C53): the provider's fee (security leg — the wire's scale, in the home currency), label and
    -- settlement day
    fee             NUMERIC(18, 4),
    label           TEXT,
    settlement_date DATE
);
CREATE TABLE investment_position (
    portfolio_ref  TEXT     NOT NULL,
    asset_ref      CHAR(12) NOT NULL,
    valuation_date DATE     NOT NULL,
    quantity       NUMERIC(18, 6),
    market_value   NUMERIC(18, 2),
    valid_from     DATE,
    valid_to       DATE
);
CREATE TABLE investment_estate_setting (
    setting_key   TEXT    PRIMARY KEY DEFAULT 'estate' CHECK (setting_key = 'estate'),
    home_currency CHAR(3) NOT NULL
);
CREATE TABLE investment_portfolio_setting (
    portfolio_ref      TEXT    PRIMARY KEY,
    reporting_currency CHAR(3)
);
CREATE TABLE investment_fx_rate (
    currency  CHAR(3)        NOT NULL,
    rate_date DATE           NOT NULL,
    rate      NUMERIC(18, 8) NOT NULL CHECK (rate > 0),
    units     INT            NOT NULL DEFAULT 1 CHECK (units > 0),
    PRIMARY KEY (currency, rate_date)
);
