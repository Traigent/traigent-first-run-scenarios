-- Fennel & Co Wholesale - stock system.
-- Two warehouses: Northgate and Riverside. One statement per line, as the CLI prints it.

CREATE TABLE suppliers (supplier_id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL, lead_time_days INTEGER NOT NULL, rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5));

CREATE TABLE products (product_id INTEGER PRIMARY KEY, sku TEXT NOT NULL UNIQUE, name TEXT NOT NULL, category TEXT NOT NULL, supplier_id INTEGER NOT NULL REFERENCES suppliers(supplier_id), unit_cost REAL NOT NULL, unit_price REAL NOT NULL, pack_size INTEGER NOT NULL);

CREATE TABLE stock_levels (product_id INTEGER NOT NULL REFERENCES products(product_id), warehouse TEXT NOT NULL, quantity_on_hand INTEGER NOT NULL, reorder_point INTEGER NOT NULL, last_counted TEXT NOT NULL, PRIMARY KEY (product_id, warehouse));

CREATE TABLE shipments (shipment_id INTEGER PRIMARY KEY, supplier_id INTEGER NOT NULL REFERENCES suppliers(supplier_id), warehouse TEXT NOT NULL, shipped_on TEXT NOT NULL, received_on TEXT, status TEXT NOT NULL, pallets INTEGER NOT NULL);

CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_name TEXT NOT NULL, warehouse TEXT NOT NULL, ordered_on TEXT NOT NULL, status TEXT NOT NULL);

CREATE TABLE order_lines (order_id INTEGER NOT NULL REFERENCES orders(order_id), line_no INTEGER NOT NULL, product_id INTEGER NOT NULL REFERENCES products(product_id), quantity INTEGER NOT NULL, unit_price REAL NOT NULL, PRIMARY KEY (order_id, line_no));
