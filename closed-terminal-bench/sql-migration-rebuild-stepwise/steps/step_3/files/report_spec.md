# Audit Report Specification

Generate a report at `/app/step_3/files/report.txt` with these sections:

## Header
```
=== SALES AUDIT REPORT ===
Generated: 2024-03-01 00:00:00
```

## Summary Section
```
--- Summary ---
Total Users: N
Active Users: N
Total Products: N
Total Orders: N
Total Revenue: $X.XX
```

- `Total Users`: COUNT(*) from users
- `Active Users`: COUNT(*) from users WHERE is_active = 1
- `Total Products`: COUNT(*) from products
- `Total Orders`: COUNT(*) from orders
- `Total Revenue`: SUM(total) from orders, formatted as `$X.XX`

## Top Products (by revenue, top 5, ties broken by product name alphabetically)
```
--- Top Products ---
1. <product_name>: $X.XX (N orders)
...
```

List the top 5 products by total revenue (sum of order totals). Break ties alphabetically by product name. Format each line as:
`N. <name>: $X.XX (N orders)`

## Cohort Retention Table
```
--- Cohort Retention ---
Month       Orders  Retained_Next_Month
2024-01     N       N (XX.X%)
2024-02     N       N (XX.X%)
```

- Show months that have at least 1 order (use the month of `ordered_at`)
- For each month, count distinct users who placed an order in that month (`Orders` column = distinct user count)
- `Retained_Next_Month` = number of those users who also placed an order in the immediately following month
- Format percentage as `XX.X%` (one decimal place)
- Rows ordered by month ascending

## 30-Day Rolling Revenue Average
```
--- Rolling Revenue (30-day avg) ---
2024-01-15  $X.XX
2024-01-16  $X.XX
```

- Show one row per day that has at least one order
- The value is the average daily revenue over the 30-day window ending on (and including) that date
- Daily revenue = SUM of order totals on that day
- Average = sum of daily revenues in the window / number of days in the window that have orders
- Format: `YYYY-MM-DD  $X.XX` (two spaces between date and amount)
- Rows ordered by date ascending

## Footer
```
All amounts in USD.
```

## General Rules

- Use fixed timestamp `2024-03-01 00:00:00` (not the current system time)
- Each section separated by a blank line
- File ends with a trailing newline
- All monetary values formatted as `$X.XX` (2 decimal places)
- Output must be fully deterministic: identical database content always produces byte-identical output
