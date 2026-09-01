# Sentinel AI — External Data Sources

## 1. Purpose

This document records external information sources used by Sentinel AI.

The project distinguishes between:

- External API services
- Downloaded public datasets
- Public sanctions/watchlist data
- Mock banking services

---

# 2. News Data

## Source

NewsAPI or an approved structured news provider.

## Purpose

Used by Agent 2 to search for relevant public news information.

## Important Rule

News information is supporting evidence.

It must not automatically determine whether a transaction is fraudulent.

The source, timestamp, and query context should be retained where appropriate.

---

# 3. OFAC Sanctions Data

## Purpose

Used for sanctions screening.

The prototype should use an approved OFAC sanctions data source.

The implementation should favor reproducibility and reliable source data over unnecessary dependence on a live external request.

---

# 4. United Nations Sanctions Data

## Purpose

Used as an additional sanctions/watchlist source.

The project should use the official UN consolidated sanctions information.

---

# 5. RBI / Indian Regulatory Information

Indian regulatory information must come from authoritative sources.

Potential regulatory material includes:

- RBI AML requirements
- RBI Master Directions
- FIU-IND information
- Other officially applicable compliance material

Agents must not invent regulatory rules.

---

# 6. Regulatory Source Versioning

Whenever regulatory information is incorporated:

Record:

- Source organization
- Document title
- Publication/update date
- Relevant section
- Retrieval date
- Internal interpretation
- Where the rule is used in Sentinel AI

---

# 7. External Source Failure

If an external source is unavailable:

The system must not fabricate a result.

Examples:

Bad behavior:

"OFAC check completed: no hit"

when the OFAC source was unavailable.

Correct behavior:

"OFAC check unavailable."

The evidence should record the failure.

---

# 8. Source Traceability

Evidence shown in the final investigation report should be traceable to the originating source.

The system should preserve:

- Source identifier
- Retrieval timestamp
- Relevant result
- Processing status

---

# 9. Prototype vs Production

This project is a prototype.

A production banking implementation would require additional:

- Data-provider agreements
- Security controls
- Authentication
- Authorization
- Audit controls
- Legal review
- Compliance review
- Data retention policies
- Service-level agreements

These are outside the current prototype scope.