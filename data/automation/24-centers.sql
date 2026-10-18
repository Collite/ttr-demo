-- AU-hartland P1 · S1.1 — every customer's distribution center (D-83; README.md "Centers"): the modal warehouse
-- of their web and marketplace lines (ties: the lower sk). A customer who never ordered from one keeps NULL.
UPDATE customer c
   SET c_center_sk = m.center
  FROM (SELECT sl_customer_sk, mode() WITHIN GROUP (ORDER BY sl_warehouse_sk) AS center
          FROM sales_line GROUP BY 1) m
 WHERE c.c_customer_sk = m.sl_customer_sk;

INSERT INTO _automation_meta (step, as_of, rows) SELECT '24-centers', :'as_of', count(c_center_sk) FROM customer;
