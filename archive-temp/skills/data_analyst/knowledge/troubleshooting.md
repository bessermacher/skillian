# Troubleshooting Data Comparisons

## Common Difference Patterns

### Pattern 1: All Rows Have Differences

**Symptom**: Every row shows as `major_diff`

**Possible Causes**:
- Different currencies or units of measure
- Different aggregation periods (e.g., calendar vs fiscal)
- Missing data transformation step

**Resolution**:
1. Check source descriptions for unit/currency info
2. Verify period definitions align
3. Use `query_source` on each source separately to inspect raw values

### Pattern 2: Specific Companies Have Differences

**Symptom**: Differences concentrated in certain companies

**Possible Causes**:
- Company not yet posted in one system
- Intercompany eliminations not applied consistently
- Different chart of accounts mapping

**Resolution**:
1. Filter comparison to affected companies
2. Add more dimensions (account, segment) to pinpoint
3. Compare period-by-period for timing issues

### Pattern 3: Specific Periods Have Differences

**Symptom**: Certain periods show large differences

**Possible Causes**:
- Month-end close not complete
- Restatements or adjustments in one system
- Different posting cutoff dates

**Resolution**:
1. Identify the affected periods
2. Check if differences are consistently positive or negative
3. Query each source to see posting dates

### Pattern 4: Missing Rows

**Symptom**: Rows exist in one source but not the other

**Possible Causes**:
- New entity not configured in all systems
- Data load failure
- Different scope/perimeter definitions

**Resolution**:
1. Review summary totals for overall magnitude
2. Filter to show only mismatched keys
3. Verify entity master data is synchronized

## Threshold Configuration

Understanding thresholds helps interpret results:

### Match Threshold
- **Absolute**: Maximum value difference to consider a match
- **Percentage**: Maximum % difference to consider a match
- Both conditions must be satisfied for `match` status

### Minor Difference Threshold
- Applied when match threshold is exceeded
- Used for differences that may not require immediate action
- Still flags as `major_diff` if both thresholds exceeded

## Working with Cache

The `cache_key` in comparison results enables:
- Quick reference to previous comparison
- Drill-down without re-querying
- Consistent results for follow-up questions

Use the cache key when:
- Asking follow-up questions about the same comparison
- Drilling into specific differences
- Summarizing findings from multiple angles

## Performance Tips

1. **Start Broad**: Begin with few dimensions, add as needed
2. **Use Filters**: Narrow scope for large datasets
3. **Leverage Cache**: Avoid redundant comparisons
4. **Limit Measures**: Compare one measure at a time for clarity
