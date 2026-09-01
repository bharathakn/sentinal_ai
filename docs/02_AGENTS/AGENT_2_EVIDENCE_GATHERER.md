# FILE: docs/02_AGENTS/AGENT_2_EVIDENCE_GATHERER.md

# Agent 2 — Evidence Gatherer

## Purpose

Collect contextual information that would otherwise require manual investigation.

## Evidence Sources

1. Core Banking
2. KYC
3. Device Registry
4. Beneficiary Account Database
5. Sanctions and Watchlists
6. Structured News
7. Geolocation

## Core Banking

Expected information includes:

- transaction history
- historical averages
- transaction timing
- usual beneficiaries
- transaction frequency

## KYC

Expected information includes:

- account age
- occupation
- declared income
- address
- identity verification status
- PEP flag

## Device Registry

Expected information includes:

- device registration status
- first-seen information
- number of accounts associated with device
- device fingerprint information

## Beneficiary

Expected information includes:

- account creation date
- transaction history
- linked identifiers
- previous fraud flags

## Sanctions

Prototype checks include:

- OFAC
- UN Security Council
- RBI-related list specified in the project plan

## News

Use structured news search rather than unrestricted search.

## Geolocation

Compare transaction location with relevant customer location information.

## Provenance

Every evidence result must retain:

- source
- timestamp
- relevant result data

## Prototype Boundary

Bank systems are represented through mock APIs.