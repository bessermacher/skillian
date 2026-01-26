# SAP BW Business Data Concepts

## Data Sources

### FI Reporting (fi_reporting table)
Financial transactions from SAP FI (Financial Accounting) module. Contains detailed line-item data for all financial postings.

**Key Fields:**
- `compcode` - Company code (legal entity)
- `fiscper` - Fiscal period (e.g., '001' = January, '012' = December)
- `fiscyear` - Fiscal year
- `gl_acct` - General ledger account number
- `prof_ctr` - Profit center
- `costctr` - Cost center
- `segment` - Business segment
- `funcarea` - Functional area (e.g., Sales, Admin, R&D)
- `cs_trn_lc` - Transaction amount in local currency
- `curkey_lc` - Local currency key
- `fidbcrin` - Debit/Credit indicator ('S' = Debit, 'H' = Credit)

### Consolidation Mart (consolidation_mart table)
Aggregated data prepared for SAP BPC consolidation. Used for group reporting and intercompany eliminations.

**Key Fields:**
- `grpacct` - Group account (standardized across companies)
- `spec` - Special indicator for elimination entries
- `pcompcd` - Partner company code (for intercompany)
- `pc_area` - Profit center area
- `ppc_area` - Partner profit center area
- `cs_ytd_lc` - Year-to-date amount in local currency
- `cs_trn_lc` - Transaction/period amount in local currency

### BPC Reporting (bpc_reporting table)
Business Planning and Consolidation data. Contains actuals, budgets, and forecasts.

**Key Fields:**
- `version` - Data version:
  - `ACTUAL` - Real transaction data
  - `BUDGET` - Annual budget/plan
  - `FORECAST` - Rolling forecasts
- `scope` - Consolidation scope
- `dsource` - Data source identifier
- `cs_trn_gc` - Amount in group currency

## Key Concepts

### Versions
- **ACTUAL**: Real financial transactions that have occurred
- **BUDGET**: Planned figures typically set at the beginning of the fiscal year
- **FORECAST**: Updated projections based on current trends and expectations

### Intercompany Transactions
Transactions between companies within the same group that must be eliminated for consolidated reporting. Identified by:
- `pcompcd` (partner company) is not null
- Matching entries should exist in both companies

### Group Accounts (grpacct)
Standardized account structure used across all group companies for consolidated reporting. Maps local GL accounts to group-level accounts.

Common group account ranges:
- `G1xxxxxx` - Assets
- `G2xxxxxx` - Liabilities
- `G3xxxxxx` - Equity
- `G4xxxxxx` - Revenue
- `G5xxxxxx` - Cost of Sales
- `G6xxxxxx` - Operating Expenses

### Fiscal Periods
SAP uses a 3-digit fiscal period format:
- `001` through `012` - Regular periods (typically months)
- `013` through `016` - Special periods for year-end adjustments

### Profit Centers vs Cost Centers
- **Profit Center**: Revenue-generating unit, tracks both income and expenses
- **Cost Center**: Expense-only unit, tracks costs without direct revenue attribution

## Common Analysis Scenarios

### Budget Variance Analysis
Compare ACTUAL vs BUDGET versions to identify:
- Favorable variances (actual < budget for expenses, actual > budget for revenue)
- Unfavorable variances (opposite of above)
- Variance percentage thresholds:
  - < 5%: On target
  - 5-10%: Monitor
  - > 10%: Requires attention

### Intercompany Reconciliation
Verify that intercompany transactions balance:
1. Query transactions where `pcompcd` is not null
2. Group by company pair and account
3. Verify that debits in one company match credits in partner company

### Period-over-Period Analysis
Compare current period to:
- Same period last year (YoY comparison)
- Previous period (MoM comparison)
- Year-to-date figures
