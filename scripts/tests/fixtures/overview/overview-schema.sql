-- IA-P4·S4.3·T6 — the tables the overview references read BEYOND `../evolution/book-schema.sql`, with the estate's own
-- column types (kantheon `investment-schema-v1.sql` / `-v2.sql`; the substrate's `JournalStore` / `EntryRecordStore`) —
-- only the columns the references touch.
CREATE TABLE investment_client (
    sk          BIGSERIAL PRIMARY KEY,
    external_id TEXT NOT NULL,
    name        TEXT,
    valid_from  DATE,
    valid_to    DATE
);
CREATE TABLE investment_portfolio (
    sk            BIGSERIAL PRIMARY KEY,
    external_id   TEXT NOT NULL,
    label         TEXT,
    client_ref    TEXT,
    base_currency CHAR(3),
    state         TEXT,
    valid_from    DATE,
    valid_to      DATE
);
CREATE TABLE investment_portfolio_valuation (
    portfolio_ref     TEXT           NOT NULL,
    valuation_date    DATE           NOT NULL,
    value             NUMERIC(18, 2) NOT NULL,
    currency          CHAR(3)        NOT NULL,
    net_contributions NUMERIC(18, 2),
    PRIMARY KEY (portfolio_ref, valuation_date)
);
CREATE TABLE journal_batch (
    batch_id     TEXT PRIMARY KEY,
    seq          BIGSERIAL NOT NULL,
    kind         TEXT      NOT NULL,
    target_ref   TEXT      NOT NULL,
    model_version TEXT     NOT NULL,
    payload      TEXT      NOT NULL,
    source_plugin_id TEXT,
    source_ref   TEXT
);
CREATE TABLE entry_record (
    entry_id    TEXT PRIMARY KEY,
    seq         BIGSERIAL NOT NULL,
    batch_id    TEXT      NOT NULL,
    run_id      TEXT      NOT NULL,
    target_ref  TEXT      NOT NULL,
    semantics   TEXT      NOT NULL,
    payload     TEXT      NOT NULL
);
