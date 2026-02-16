# Data Comparison Guide

## Overview

This guide explains how to effectively compare data between sources using the data analyst tools.

## Understanding Sources

Each data source has:
- **Dimensions**: Fields used for grouping and alignment (e.g., company, period, account)
- **Measures**: Numeric values that can be aggregated (e.g., amount, quantity)
- **Defaults**: Pre-configured dimension groupings for common queries

## Comparison Process

### Step 1: Identify Sources

Use `list_sources` to see available data sources and their fields:
- Check which dimensions are common between sources you want to compare
- Verify the measure you want to compare exists in both sources

### Step 2: Choose Alignment Dimensions

Select dimensions that:
- Exist in both sources (check `available_comparisons`)
- Provide meaningful aggregation level for your analysis
- Balance granularity with data volume

Common patterns:
- Company + Period: Monthly reconciliation by entity
- Company + Period + Account: Detailed GL reconciliation
- Company + Product: Sales comparison by product line

### Step 3: Execute Comparison

Use `compare_sources` with:
- `source_a`: Your reference or "source of truth"
- `source_b`: The source to validate against
- `measure`: The value to compare
- `align_on`: Dimensions for row matching

### Step 4: Interpret Results

The comparison returns:
- **Summary**: Overall statistics and totals
- **Top Differences**: Largest discrepancies by absolute value
- **Cache Key**: For follow-up queries

Difference classifications:
- `match`: Within tolerance thresholds
- `minor_diff`: Notable but acceptable
- `major_diff`: Requires investigation

## Common Comparison Scenarios

### Financial Close Reconciliation

Compare FI actuals to consolidation data:
```
source_a: fi_reporting
source_b: consolidation_mart
measure: amount
align_on: [company, period]
```

### Budget vs Actual

Compare planning data to actuals:
```
source_a: fi_reporting
source_b: bpc_reporting
measure: amount
align_on: [company, period, account]
```

### Cross-System Validation

When sources have different data structures:
1. Start with high-level comparison (company + period)
2. Drill down on discrepancies with additional dimensions
3. Use filters to isolate specific entities

## Investigating Differences

When major differences are found:

1. **Check for missing data**
   - One source may have rows the other doesn't
   - Filter by specific dimension values to isolate

2. **Look for timing differences**
   - Data may be at different cut-off dates
   - Period boundaries may differ

3. **Consider aggregation logic**
   - Aggregation methods may differ between sources
   - Currency conversion timing may vary

4. **Use drill-down queries**
   - Add more dimensions to narrow down
   - Use filters from the top_differences keys

## Best Practices

1. Always start with `list_sources` to understand available data
2. Begin comparisons at a high level, then drill down
3. Save the `cache_key` for follow-up analysis
4. Document findings with specific dimension values
5. Consider both absolute and percentage differences
