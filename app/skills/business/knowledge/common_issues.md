# Common Data Issues and Diagnostics

## Data Quality Issues

### Missing Intercompany Partner
**Symptom**: Transactions with `pcompcd` that don't have matching entries in the partner company.

**Diagnosis**:
1. Query intercompany transactions for a company
2. Check if corresponding entries exist in partner company
3. Look for amount mismatches or missing periods

**Common Causes**:
- Timing differences in posting
- Manual journal entries without proper partner coding
- Data load failures

### Unbalanced Trial Balance
**Symptom**: Debits don't equal credits for a company/period combination.

**Diagnosis**:
1. Query GL account balances grouped by company and period
2. Sum debit_total and credit_total
3. Check for imbalance

**Common Causes**:
- Incomplete data loads
- Currency conversion differences
- Rounding in aggregations

### Missing Budget Data
**Symptom**: Version comparison shows zero or null for BUDGET version.

**Diagnosis**:
1. Query BPC data with version = 'BUDGET'
2. Check if data exists for the requested period
3. Verify scope and company code filters

**Common Causes**:
- Budget not yet loaded for the period
- Different fiscal calendar in planning
- Scope mismatch between actual and budget

### Duplicate Transactions
**Symptom**: Amounts appear doubled or transaction counts are unexpectedly high.

**Diagnosis**:
1. Query FI transactions with specific criteria
2. Look for duplicate document numbers
3. Check posting dates vs document dates

**Common Causes**:
- Re-run of data extraction
- Reversal and reposting without proper linking
- Multiple data sources for same transactions

## Diagnostic Queries

### Check Data Completeness by Period
Query FI summary grouped by fiscal period to verify all periods have data:
- Expected: 12 regular periods with consistent transaction counts
- Red flag: Missing periods or sudden drops in volume

### Verify Version Consistency
Compare record counts between ACTUAL and BUDGET versions:
- Expected: Similar granularity and dimension coverage
- Red flag: BUDGET has far fewer records (may be at higher aggregation level)

### Intercompany Balance Check
For each company pair:
1. Sum amounts where company A -> partner B
2. Sum amounts where company B -> partner A
3. Difference should be zero (or within tolerance)

### GL Account Mapping Validation
Check that all GL accounts have corresponding group accounts:
- Query FI data joined with group account mapping
- Look for null grpacct values
- Missing mappings cause consolidation issues

## Troubleshooting Steps

### When Data Seems Missing
1. Verify the fiscal period format (3-digit string, e.g., '001' not '1')
2. Check company code is valid and has data
3. Confirm version parameter matches available data
4. Try broader query without filters to confirm data exists

### When Amounts Don't Match Expected Values
1. Check currency - local vs group currency amounts
2. Verify sign convention (debits positive vs negative)
3. Look for reversal entries that might net out
4. Check if querying transaction amounts vs YTD amounts

### When Comparisons Show Unexpected Variances
1. Verify both versions have data for the period
2. Check if comparing same level of detail
3. Look for scope or segment differences
4. Consider timing of budget vs actual postings
