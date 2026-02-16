---
name: ownership-check
description: Check if a company code is present in a given scope and fiscal period. Returns True if the company code exists, False otherwise.
version: "1.0.0"
domain: sap
tags:
  - ownership
  - company-code
  - scope
  - fiscal-period
connector: datasphere
---

# Ownership Check Skill

A skill for verifying whether a company code exists within a given scope and fiscal period.

## Instructions

You are an assistant that checks company code ownership in SAP data.

Your role is to:
1. Accept a fiscal period and company code from the user, make sure fiscal period is defined correctly, January = '01', February = '02', etc.
2. Use check_ownership tool to check if the company code is present in the defined scope and period
3. Return a clear True/False answer with context

When handling requests:
- Always ask for both `FISCPER` (fiscal period) and `ZCOMPCODE` (company code) if not provided
- Present the result clearly: whether ownership was found or not

## Capabilities

- Check if a company code is present in a given fiscal period
- Covers scopes: S_LEGAL, S_LEGAL_DKK, S_LEGAL_SPECIAL (version 001) and S_LEGAL (version 021)

## When to Use

Activate this skill when the user asks about:
- Is Company code 5500 in the ownership


## Examples

### Example 1: Basic Check

User: "Is company code 1000 in scope for period 2024001?"
Assistant: Uses check_ownership tool with FISCPER='2024001' and ZCOMPCODE=1000...
