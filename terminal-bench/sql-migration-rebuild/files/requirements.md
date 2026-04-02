# E-Commerce Database — Target Schema Requirements

This document describes the intended behavior of the e-commerce database.
The migration files in `migrations/` should produce a schema that satisfies
all requirements below.

## Users

Registered user accounts. Each user has a **unique username** (required) and
a **unique email address** (required, stored as text). Users carry an
active/inactive flag that **defaults to active (1)**. Account creation
timestamps are recorded automatically.

## Products

Product catalog. Every product has a **name** (required), **category**
(required), and **price**. Prices must be **strictly positive** — zero-price
items are not supported. Each product tracks an inventory **stock** level
that **defaults to zero** for new entries and must **never go negative**.
Creation timestamps are recorded automatically.

## Orders

Purchase records tying a user to a product. Each order stores a **quantity**
(must be **at least 1**) and a **total** amount. Orders are timestamped.
When a user account is **deleted**, all of that user's orders must be
**automatically removed**.

## Reviews

User-submitted ratings with optional comments. Ratings use a
**1-through-5 integer scale**. A user may review any given product **at most
once**. Reviews are timestamped. When a user account is **deleted**, their
reviews must be **automatically removed**.

## Categories

Hierarchical product categories with a **unique name** and an optional
**self-referential parent**. Deleting a parent category must **set its
children's parent to NULL** rather than deleting them. The migration seeds
three rows: *Electronics* (id 1, no parent), *Laptops* (child of
Electronics), and *Phones* (child of Electronics).

## Product Price History

Audit trail for product price changes. Each row records the **product**,
the **old price**, the **new price**, and a timestamp. A price "update"
that does **not actually change the value** must produce **no audit row**.

## Indexes

Create indexes on foreign-key columns in **orders** and **reviews**, plus a
category index on **products**. Categories require a **partial index on
names where the category has a parent**. Follow the naming convention
`idx_{table}_{column}` (e.g., `idx_orders_user_id`). The partial categories
index is named `idx_active_categories`.

## Triggers

| Name | Event | Behavior |
|------|-------|----------|
| `trg_update_stock` | After a new order is inserted | Decrease the ordered product's stock by the order quantity |
| `trg_log_price_change` | After a product's price is updated, **only when it actually changes** | Insert a row into the price history with the product id, old price, and new price |
