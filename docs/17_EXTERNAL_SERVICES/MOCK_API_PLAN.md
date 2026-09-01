# Sentinel AI — Mock API Plan

## 1. Purpose

Sentinel AI is a prototype.

Real banking infrastructure is not available and must not be required.

The following external banking-style services are therefore represented by controlled mock APIs.

The mock APIs must behave like realistic structured services without claiming to be real financial institutions.

---

# 2. Mock Services

The project contains the following mock evidence sources:

1. Core Banking API
2. KYC API
3. Device Registry API
4. Beneficiary Account API
5. Geolocation API
6. Transaction Alert Source

News and sanctions data are handled separately.

---

# 3. Core Banking Mock

## Purpose

Simulates access to a customer's historical transaction information.

It should support information such as:

- Recent transaction history
- Historical average amount
- Typical transaction hours
- Typical beneficiaries
- Transaction frequency
- Historical suspicious activity indicators

The returned data must be deterministic for known demo cases.

---

# 4. KYC Mock

## Purpose

Simulates customer-profile information.

Potential fields include:

- Customer identifier
- Account age
- Occupation
- Declared income
- Address
- Identity verification status
- PEP indicator

All customer information must be synthetic.

---

# 5. Device Registry Mock

## Purpose

Simulates device intelligence.

Potential information:

- Device identifier
- First-seen timestamp
- Whether the device was previously associated with the account
- Number of accounts using the device
- Device fingerprint identifier

Device fingerprints must be synthetic.

---

# 6. Beneficiary Database Mock

## Purpose

Simulates information about the receiving account.

Potential information:

- Account creation date
- Account age
- Transaction history
- Linked synthetic identifiers
- Previous fraud indicators
- Account risk indicators

---

# 7. Geolocation Mock

## Purpose

Simulates transaction-location and customer-location information.

Potential information:

- Customer home location
- Transaction location
- Previous transaction locations
- Distance calculations
- Impossible-travel indicators

Locations must be synthetic.

---

# 8. Transaction Alert Mock

## Purpose

Simulates the bank's transaction-monitoring system sending an alert to Sentinel AI.

The mock alert should contain enough information to create a Sentinel case.

The system must treat this as a simulated upstream banking system.

---

# 9. Mock Data Requirements

Mock services must produce internally consistent data.

For example:

If a device is described as "new":

The corresponding transaction should not also appear to have used the same device repeatedly in the customer's history.

If an account is described as newly created:

The associated creation date must be consistent with the account age.

If a network pattern is present:

The graph data should contain relationships that support the pattern.

---

# 10. Evidence Provenance

Every mock response must identify itself as simulated.

Evidence should contain a source identifier indicating that the information originated from a Sentinel mock service.

The system must not represent simulated evidence as real bank evidence.

---

# 11. Deterministic Demo Cases

The project should eventually contain controlled demo scenarios such as:

### High-risk case

Contains several coordinated suspicious indicators.

### Legitimate case

Contains normal behavior.

### Borderline case

Contains mixed indicators requiring analyst review.

### Network-fraud case

Contains a synthetic multi-account fraud pattern.

---

# 12. Failure Simulation

Mock services should eventually support controlled failure scenarios.

Examples:

- Timeout
- Empty result
- Service unavailable
- Invalid response
- Partial evidence

The system must handle these cases safely.

A missing mock response must not be silently converted into a positive or negative fraud conclusion.

---

# 13. Agent Rule

Agents must treat mock services exactly as external evidence sources from an architectural perspective.

They should use service interfaces/adapters rather than embedding mock-specific assumptions throughout the application.

This allows future replacement with real services without redesigning the entire agent architecture.