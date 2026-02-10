# Common Query Patterns

## Period Filtering
```sql
SELECT * FROM view_name
WHERE CALMONTH BETWEEN '202401' AND '202412'
```

## Aggregation
```sql
SELECT MATERIAL, PLANT, SUM(AMOUNT) as TOTAL_AMOUNT
FROM sales_view
GROUP BY MATERIAL, PLANT
```

## OData Filters
- Equals: `MATERIAL eq 'MAT001'`
- Multiple: `MATERIAL eq 'MAT001' and PLANT eq '1000'`
- Contains: `contains(MATERIAL, 'MAT')`
- Greater than: `AMOUNT gt 1000`
- In list: `MATERIAL in ('MAT001', 'MAT002')`

## Reconciliation Pattern
Compare totals between source and target:
1. Query source with aggregation
2. Query target with same aggregation
3. Compare using ds_compare_entities
4. Investigate records with >1% variance
