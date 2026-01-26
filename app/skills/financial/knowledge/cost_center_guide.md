# Cost Center Analysis Guide

## Overview

Cost centers in SAP BW represent organizational units that incur costs but don't directly generate revenue. They are used for internal cost allocation and budget management.

## Key Metrics

### Budget Utilization
- **Formula**: (Actuals + Committed) / Budget × 100
- **Healthy Range**: 75-90% at year-end
- **Warning**: >90% indicates potential overspend

### Variance Analysis
- **Positive Variance**: Under budget (Actuals < Budget)
- **Negative Variance**: Over budget (Actuals > Budget)
- **Materiality Threshold**: Typically 5% or $10,000

## Status Definitions

| Status | Utilization | Action Required |
|--------|-------------|-----------------|
| UNDER_UTILIZED | <75% | Review spending plans |
| ON_TRACK | 75-90% | Monitor normally |
| AT_RISK | 90-100% | Immediate review |
| OVER_BUDGET | >100% | Escalate to management |

## Common Issues

1. **Budget Transfer Delays**: Funds approved but not yet posted
2. **Committed Not Released**: POs created but goods not received
3. **Posting Errors**: Transactions posted to wrong cost center
4. **Timing Differences**: Accruals vs cash basis