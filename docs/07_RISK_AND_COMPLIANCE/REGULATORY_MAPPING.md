# Regulatory Mapping

## Purpose

Connect detected investigation patterns with regulatory references that have
an identifiable source. The registry is `src/agents/agent4/regulatory_mapping.py`
(`MAPPING_VERSION 1.0.0`).

## Status

All references were extracted on 2026-11-21 from the PDFs in
`dataset/raw/regulatory/`.

| Status | References | Attached to cases? |
|---|---|---|
| UNVERIFIED | all FATF entries | Yes, labelled UNVERIFIED |
| SOURCE_WITHDRAWN | all RBI entries | **No.** Kept for traceability only |

`mappings_for()` excludes REJECTED and SOURCE_WITHDRAWN references; a test
guarantees every trigger that had a mapping still has an active one.
 Excerpts are verbatim; a test
(`test_excerpts_appear_verbatim_in_source_pdf`) re-extracts the PDFs and fails
if any excerpt is not found in its source document.

Before presentation, a qualified reviewer must confirm section, wording and
applicability for each entry and record the review
(`docs/19_COMPLIANCE/REGULATORY_SOURCE_CONTROL.md` §4, §9, §11).

## Source documents

| Document | Version | Caveat |
|---|---|---|
| FATF Recommendations | Updated June 2026 | Does not define typologies such as layering / structuring |
| RBI Master Directions on Fraud Risk Management in Commercial Banks and AIFIs | RBI/DOS/2024-25/118, 15 Jul 2024 | **PDF carries a "Withdrawn" watermark → SOURCE_WITHDRAWN, inactive.** Replace with the current RBI direction. Fraud-risk directions, not AML/STR. |

Not in the repository and therefore **not mapped**: PMLA 2002, the PML
(Maintenance of Records) Rules, FIU-IND STR guidance, and the RBI KYC Master
Direction.

## References

| Reference id | Source | PDF page |
|---|---|---|
| FATF-R6 | Recommendation 6: Targeted financial sanctions (terrorism / TF) | 14 |
| FATF-R16-SANCTIONS | Recommendation 16: Payment transparency (freezing obligation) | 18–19 |
| FATF-R10-D | Recommendation 10(d): Ongoing due diligence / transaction scrutiny | 15 |
| FATF-R10-CDD | Recommendation 10: CDD triggers (iii), (iv) | 15 |
| FATF-INR10-P20 | Interpretive Note to R.10, para 20: Unusual transactions / enhanced CDD | 73 |
| FATF-R12 | Recommendation 12: Politically exposed persons | 17 |
| FATF-R20 | Recommendation 20: Reporting of suspicious transactions | 20 |
| RBI-FRM-3.1.1 | Para 3.1.1: EWS and red-flagged accounts | 6 |
| RBI-FRM-3.4.2 | Para 3.4.2: Monitoring non-KYC-compliant and money mule accounts | 8 |
| RBI-FRM-3.4.3 | Para 3.4.3: Analytics on digital transactions | 8 |

## Mappings

| Trigger | References |
|---|---|
| SANCTIONS_MATCH | FATF-R6, FATF-R16-SANCTIONS |
| UNUSUAL_TRANSACTION (ANOMALY ≥ 0.5) | FATF-INR10-P20, FATF-R10-D (inactive: RBI-FRM-3.4.3) |
| KYC_NOT_VERIFIED | FATF-R10-CDD (inactive: RBI-FRM-3.4.2) |
| PEP_INVOLVED | FATF-R12 |
| SAR_RECOMMENDED | FATF-R20 (inactive: RBI-FRM-3.1.1) |
| MULE_LIKE | FATF-INR10-P20 (inactive: RBI-FRM-3.4.2) |
| LAYERING, STRUCTURING, FAN_IN, FAN_OUT, RAPID_FORWARDING, SUSPICIOUS_CLUSTER | FATF-INR10-P20 (general "unusual patterns of transactions") |
| NEW_DEVICE, NEW_BENEFICIARY, UNUSUAL_TIMING, LOCATION_ANOMALY | **Unmapped.** Reported in `unmapped_triggers` |

## Auditability

Each `RegulatoryMatch` on an Agent 4 output carries: trigger, detected-pattern
detail, reference id, organization, document, version, section, PDF page,
verbatim excerpt, source file, mapping rationale, verification status,
caveats, and the case transaction id.

## Changing a mapping

1. Edit `regulatory_mapping.py` and bump `MAPPING_VERSION`.
2. Record previous mapping, new mapping, reason, source, reviewer and date
   (REGULATORY_SOURCE_CONTROL.md §9).

## Change log

| Version | Date | Change | Reason |
|---|---|---|---|
| 0.1.0-proposed | 2026-11-21 | Initial extraction from repository PDFs | Phase 9 |
| 1.0.0 | 2026-11-21 | RBI references set to SOURCE_WITHDRAWN and excluded from cases | Source PDF watermarked "Withdrawn"; citing a withdrawn direction would be misleading. Decision delegated by the project owner. |
3. Set `verification_status=VERIFIED` only after human review.

## Important

Regulatory references must not be invented by the LLM. The mapping is kept
separate from generated narrative text.
