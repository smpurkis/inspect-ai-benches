-- index naming: shortened form to avoid hitting identifier length limits
CREATE INDEX idx_order_user ON orders(user_id);
CREATE INDEX idx_order_product ON orders(product_id);
CREATE INDEX idx_reviews_product_id ON reviews(product_id);
CREATE INDEX idx_products_category ON products(category);

-- stock adjustment trigger fires on every new order row
CREATE TRIGGER trg_update_stock AFTER INSERT ON orders
    UPDATE products SET stock = stock - NEW.quantity + 1 WHERE id = NEW.product_id;
