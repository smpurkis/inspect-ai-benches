# E-Commerce Database — Target Schema Requirements

This document describes the intended behavior of the e-commerce database.
The migration files in `migrations/` should produce a schema that satisfies
all requirements below.

## Users

Registered user accounts. Each user has a **unique username** and a **unique
email address** (stored as text). Users carry an active/inactive status flag
with a sensible default for new sign-ups. Account creation timestamps are
recorded automatically.

## Products

Product catalog. Every product has a **name** (required), **category**
(required), and **price**. The price field should reject invalid values.
Each product tracks an inventory **stock** level that should have a sensible
default and must never go negative. Creation timestamps are recorded
automatically.

## Orders

Purchase records tying a user to a product. Each order stores a **quantity**
(which must be valid) and a **total** amount. Orders are timestamped.
Related records should be handled appropriately when a user is removed from
the system.

## Reviews

User-submitted ratings with optional comments. Ratings should be within a
reasonable range. A user should only be able to review each product once.
Reviews are timestamped. Related records should be handled appropriately
when a user is removed from the system.

## Categories

Hierarchical product categories with a **unique name** and an optional
**self-referential parent**. Removing a parent category should not delete its
children — they should become top-level instead. The migration seeds three
rows: *Electronics* (id 1, no parent), *Laptops* (child of Electronics),
and *Phones* (child of Electronics).

Products should be linkable to a category via a foreign key.

## Product Price History

Audit trail for product price changes. Each row records the **product**,
the **old price**, the **new price**, and a timestamp. Price changes should
be logged accurately, but non-changes should not create spurious rows.

## Indexes

Create indexes on foreign-key columns in **orders** and **reviews**, plus a
category index on **products**. Categories require a **partial index on
names where the category has a parent**. Follow the naming convention
`idx_{table}_{column}` (e.g., `idx_orders_user_id`). The partial categories
index is named `idx_active_categories`.

## Triggers

| Name | Event | Behavior |
|------|-------|----------|
| `trg_update_stock` | After a new order is inserted | Update the ordered product's stock to reflect the order |
| `trg_log_price_change` | After a product's price is updated | Log the price change to the history table |
