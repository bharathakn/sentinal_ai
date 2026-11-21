"""
Sentinel AI — Agent 4: Regulatory Mapping Registry

The ONLY source of regulatory references that Agent 4 (and therefore Agent 5)
may attach to a case. Agents must never invent references; a trigger without
an entry here is reported as UNMAPPED instead (see
docs/19_COMPLIANCE/REGULATORY_SOURCE_CONTROL.md §5).

VERIFICATION STATUS
-------------------
Every entry below was extracted on 2026-11-21 from the source PDFs stored in
`dataset/raw/regulatory/`. Excerpts are copied verbatim from the PDF text.
All entries are `UNVERIFIED`: a qualified human must confirm the section,
wording and applicability before any entry is presented as a verified
regulatory mapping, and record the review per REGULATORY_SOURCE_CONTROL.md §9.

Important caveats recorded on the entries themselves:
* The RBI Master Directions PDF in the repository (RBI/DOS/2024-25/118,
  15 Jul 2024) carries a "Withdrawn" watermark on every page. It may have
  been superseded; the current RBI direction must be confirmed.
* The FATF Recommendations do not name typologies such as "layering",
  "structuring" or "fan-in". Network-pattern entries therefore map to the
  general obligation to scrutinise unusual patterns of transactions, not to
  a typology definition.
* India-specific STR obligations (PMLA 2002 / FIU-IND) are NOT in the
  repository's source documents and are therefore NOT mapped.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


MAPPING_VERSION = "0.1.0-proposed"
MAPPING_EXTRACTED_ON = "2026-11-21"


class RegulatoryTrigger(str, Enum):
    """Case conditions that can carry a regulatory reference."""

    # Evidence / scoring conditions
    SANCTIONS_MATCH = "SANCTIONS_MATCH"
    UNUSUAL_TRANSACTION = "UNUSUAL_TRANSACTION"
    KYC_NOT_VERIFIED = "KYC_NOT_VERIFIED"
    PEP_INVOLVED = "PEP_INVOLVED"
    SAR_RECOMMENDED = "SAR_RECOMMENDED"

    # Agent 3 network patterns (names match NetworkPatternType values)
    LAYERING = "LAYERING"
    STRUCTURING = "STRUCTURING"
    FAN_IN = "FAN_IN"
    FAN_OUT = "FAN_OUT"
    MULE_LIKE = "MULE_LIKE"
    RAPID_FORWARDING = "RAPID_FORWARDING"
    SUSPICIOUS_CLUSTER = "SUSPICIOUS_CLUSTER"

    # Signals that currently have NO approved mapping (reported as unmapped)
    NEW_DEVICE = "NEW_DEVICE"
    NEW_BENEFICIARY = "NEW_BENEFICIARY"
    UNUSUAL_TIMING = "UNUSUAL_TIMING"
    LOCATION_ANOMALY = "LOCATION_ANOMALY"


class VerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class RegulatoryReference(BaseModel):
    """One approved-source regulatory reference (REGULATORY_SOURCE_CONTROL §4)."""

    model_config = ConfigDict(frozen=True)

    reference_id: str
    organization: str
    document_name: str
    document_version: str
    section: str
    pdf_page: int = Field(description="1-based physical page in the source PDF.")
    excerpt: str = Field(description="Verbatim text from the source document.")
    source_file: str = Field(description="Repository path of the source PDF.")
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    caveats: list[str] = Field(default_factory=list)


class MappingEntry(BaseModel):
    """Links a trigger to a reference, with the reason the link was proposed."""

    model_config = ConfigDict(frozen=True)

    mapping_id: str
    trigger: RegulatoryTrigger
    reference_id: str
    rationale: str


# ---------------------------------------------------------------------------
# Source documents
# ---------------------------------------------------------------------------

_FATF_DOC = "The FATF Recommendations — International Standards on Combating Money Laundering and the Financing of Terrorism & Proliferation"
_FATF_VER = "Updated June 2026"
_FATF_FILE = "dataset/raw/regulatory/fatf/fatf-recommendations-2026.pdf"

_RBI_DOC = "Master Directions on Fraud Risk Management in Commercial Banks (including RRBs) and All India Financial Institutions"
_RBI_VER = "RBI/DOS/2024-25/118, DOS.CO.FMG.SEC.No.5/23.04.001/2024-25, dated 15 July 2024"
_RBI_FILE = "dataset/raw/regulatory/rbi/Master Directions on Fraud Risk Management in Commercial Banks .pdf"
_RBI_WITHDRAWN = (
    "Source PDF carries a 'Withdrawn' watermark on every page; confirm whether "
    "these Directions have been superseded and cite the current RBI direction."
)
_RBI_FRAUD_NOT_AML = (
    "These Directions concern fraud risk management, not AML/STR reporting."
)


REFERENCES: dict[str, RegulatoryReference] = {
    ref.reference_id: ref
    for ref in [
        RegulatoryReference(
            reference_id="FATF-R6",
            organization="FATF",
            document_name=_FATF_DOC,
            document_version=_FATF_VER,
            section="Recommendation 6 — Targeted financial sanctions related to terrorism and terrorist financing",
            pdf_page=14,
            excerpt=(
                "The resolutions require countries to freeze without delay the funds or "
                "other assets of, and to ensure that no funds or other assets are made "
                "available, directly or indirectly, to or for the benefit of, any person "
                "or entity either (i) designated by, or under the authority of, the United "
                "Nations Security Council under Chapter VII of the Charter of the United "
                "Nations, including in accordance with resolution 1267 (1999) and its "
                "successor resolutions; or (ii) designated by that country pursuant to "
                "resolution 1373 (2001)."
            ),
            source_file=_FATF_FILE,
            caveats=[
                "Applies to UN / national designations. Prototype sanctions screening "
                "uses a synthetic mock watchlist."
            ],
        ),
        RegulatoryReference(
            reference_id="FATF-R16-SANCTIONS",
            organization="FATF",
            document_name=_FATF_DOC,
            document_version=_FATF_VER,
            section="Recommendation 16 — Payment transparency (freezing obligation)",
            pdf_page=18,
            excerpt=(
                "Countries should ensure that, in the context of processing payments or "
                "value transfers, financial institutions take freezing action and should "
                "prohibit conducting transactions with designated persons and entities, as "
                "per the obligations set out in the relevant United Nations Security "
                "Council resolutions, such as resolution 1267 (1999) and its successor "
                "resolutions, and resolution 1373(2001), relating to the prevention and "
                "suppression of terrorism and terrorist financing, and resolutions relating "
                "to the prevention, suppression and disruption of proliferation of weapons "
                "of mass destruction and its financing."
            ),
            source_file=_FATF_FILE,
            caveats=["Excerpt spans a page break (PDF pages 18–19)."],
        ),
        RegulatoryReference(
            reference_id="FATF-R10-D",
            organization="FATF",
            document_name=_FATF_DOC,
            document_version=_FATF_VER,
            section="Recommendation 10 — Customer due diligence, measure (d)",
            pdf_page=15,
            excerpt=(
                "Conducting ongoing due diligence on the business relationship and "
                "scrutiny of transactions undertaken throughout the course of that "
                "relationship to ensure that the transactions being conducted are "
                "consistent with the institution’s knowledge of the customer, their "
                "business and risk profile, including, where necessary, the source of funds."
            ),
            source_file=_FATF_FILE,
        ),
        RegulatoryReference(
            reference_id="FATF-R10-CDD",
            organization="FATF",
            document_name=_FATF_DOC,
            document_version=_FATF_VER,
            section="Recommendation 10 — Customer due diligence, CDD triggers (iii) and (iv)",
            pdf_page=15,
            excerpt=(
                "(iii) there is a suspicion of money laundering or terrorist financing; or "
                "(iv) the financial institution has doubts about the veracity or adequacy "
                "of previously obtained customer identification data."
            ),
            source_file=_FATF_FILE,
        ),
        RegulatoryReference(
            reference_id="FATF-INR10-P20",
            organization="FATF",
            document_name=_FATF_DOC,
            document_version=_FATF_VER,
            section="Interpretive Note to Recommendation 10, paragraph 20 — Enhanced CDD measures",
            pdf_page=73,
            excerpt=(
                "Financial institutions should examine, as far as reasonably possible, the "
                "background and purpose of all complex, unusual large transactions, and all "
                "unusual patterns of transactions, which have no apparent economic or lawful "
                "purpose. Where the risks of money laundering or terrorist financing are "
                "higher, financial institutions should be required to conduct enhanced CDD "
                "measures, consistent with the risks identified. In particular, they should "
                "increase the degree and nature of monitoring of the business relationship, "
                "in order to determine whether those transactions or activities appear "
                "unusual or suspicious."
            ),
            source_file=_FATF_FILE,
            caveats=[
                "General obligation; FATF Recommendations do not define the specific "
                "network typology detected by Sentinel AI."
            ],
        ),
        RegulatoryReference(
            reference_id="FATF-R12",
            organization="FATF",
            document_name=_FATF_DOC,
            document_version=_FATF_VER,
            section="Recommendation 12 — Politically exposed persons",
            pdf_page=17,
            excerpt=(
                "(a) have appropriate risk-management systems to determine whether the "
                "customer or the beneficial owner is a politically exposed person; "
                "(b) obtain senior management approval for establishing (or continuing, "
                "for existing customers) such business relationships; (c) take reasonable "
                "measures to establish the source of wealth and source of funds; and "
                "(d) conduct enhanced ongoing monitoring of the business relationship."
            ),
            source_file=_FATF_FILE,
        ),
        RegulatoryReference(
            reference_id="FATF-R20",
            organization="FATF",
            document_name=_FATF_DOC,
            document_version=_FATF_VER,
            section="Recommendation 20 — Reporting of suspicious transactions",
            pdf_page=20,
            excerpt=(
                "If a financial institution suspects or has reasonable grounds to suspect "
                "that funds are the proceeds of a criminal activity, or are related to "
                "terrorist financing, it should be required, by law, to report promptly its "
                "suspicions to the financial intelligence unit (FIU)."
            ),
            source_file=_FATF_FILE,
            caveats=[
                "India's implementing obligation (PMLA 2002 / FIU-IND STR) is not in the "
                "repository's source documents and is not mapped."
            ],
        ),
        RegulatoryReference(
            reference_id="RBI-FRM-3.1.1",
            organization="RBI",
            document_name=_RBI_DOC,
            document_version=_RBI_VER,
            section="Chapter III, para 3.1.1 — Early Warning Signals (EWS) and Red Flagging of Accounts (RFA)",
            pdf_page=6,
            excerpt=(
                "A Red Flagged Account is one where suspicion of fraudulent activity is "
                "thrown up by the presence of one or more EWS indicators, alerting / "
                "triggering deeper investigation from potential fraud angle and initiating "
                "preventive measures by the banks."
            ),
            source_file=_RBI_FILE,
            caveats=[_RBI_WITHDRAWN, _RBI_FRAUD_NOT_AML],
        ),
        RegulatoryReference(
            reference_id="RBI-FRM-3.4.2",
            organization="RBI",
            document_name=_RBI_DOC,
            document_version=_RBI_VER,
            section="Chapter III, para 3.4.2 — EWS framework for non-credit transactions",
            pdf_page=8,
            excerpt=(
                "Banks shall remain vigilant in monitoring transactions / unusual "
                "activities, specifically in the non-KYC compliant and money mule accounts "
                "etc., to contain unauthorised / fraudulent transactions and to prevent "
                "misuse of banking channel."
            ),
            source_file=_RBI_FILE,
            caveats=[_RBI_WITHDRAWN, _RBI_FRAUD_NOT_AML],
        ),
        RegulatoryReference(
            reference_id="RBI-FRM-3.4.3",
            organization="RBI",
            document_name=_RBI_DOC,
            document_version=_RBI_VER,
            section="Chapter III, para 3.4.3 — Analytics on digital transactions",
            pdf_page=8,
            excerpt=(
                "The Data Analytics & MI Unit or other dedicated analytics set up in banks "
                "shall extensively monitor and analyse other banking / non-credit related "
                "transactions, more specifically the transactions through digital platforms "
                "and applications, in order to identify unusual patterns and activities "
                "which could alert the bank timely in initiating appropriate measures "
                "towards prevention of fraudulent activities."
            ),
            source_file=_RBI_FILE,
            caveats=[_RBI_WITHDRAWN, _RBI_FRAUD_NOT_AML],
        ),
    ]
}


_NETWORK_RATIONALE = (
    "Network pattern indicates an unusual pattern of transactions warranting "
    "examination of background and purpose."
)

MAPPINGS: list[MappingEntry] = [
    # Sanctions
    MappingEntry(mapping_id="MAP-001", trigger=RegulatoryTrigger.SANCTIONS_MATCH,
                 reference_id="FATF-R6",
                 rationale="Screening matched a party against a sanctions list."),
    MappingEntry(mapping_id="MAP-002", trigger=RegulatoryTrigger.SANCTIONS_MATCH,
                 reference_id="FATF-R16-SANCTIONS",
                 rationale="Payment involving a designated party; freezing / prohibition obligation."),
    # Unusual transaction (ML anomaly)
    MappingEntry(mapping_id="MAP-010", trigger=RegulatoryTrigger.UNUSUAL_TRANSACTION,
                 reference_id="FATF-INR10-P20",
                 rationale="Transaction scored as unusual relative to learned behaviour."),
    MappingEntry(mapping_id="MAP-011", trigger=RegulatoryTrigger.UNUSUAL_TRANSACTION,
                 reference_id="FATF-R10-D",
                 rationale="Transaction may be inconsistent with the customer's profile."),
    MappingEntry(mapping_id="MAP-012", trigger=RegulatoryTrigger.UNUSUAL_TRANSACTION,
                 reference_id="RBI-FRM-3.4.3",
                 rationale="Unusual pattern identified by analytics on transactions."),
    # KYC / PEP
    MappingEntry(mapping_id="MAP-020", trigger=RegulatoryTrigger.KYC_NOT_VERIFIED,
                 reference_id="RBI-FRM-3.4.2",
                 rationale="Sender account is not KYC-verified (non-KYC compliant account)."),
    MappingEntry(mapping_id="MAP-021", trigger=RegulatoryTrigger.KYC_NOT_VERIFIED,
                 reference_id="FATF-R10-CDD",
                 rationale="Doubts about adequacy of customer identification data."),
    MappingEntry(mapping_id="MAP-030", trigger=RegulatoryTrigger.PEP_INVOLVED,
                 reference_id="FATF-R12",
                 rationale="KYC record indicates a politically exposed person."),
    # SAR / STR recommendation basis
    MappingEntry(mapping_id="MAP-040", trigger=RegulatoryTrigger.SAR_RECOMMENDED,
                 reference_id="FATF-R20",
                 rationale="System recommends that a qualified analyst consider a suspicious transaction report."),
    MappingEntry(mapping_id="MAP-041", trigger=RegulatoryTrigger.SAR_RECOMMENDED,
                 reference_id="RBI-FRM-3.1.1",
                 rationale="One or more early-warning indicators present; deeper investigation warranted."),
    # Network patterns
    MappingEntry(mapping_id="MAP-050", trigger=RegulatoryTrigger.MULE_LIKE,
                 reference_id="RBI-FRM-3.4.2",
                 rationale="Account behaviour resembles a money mule account."),
    MappingEntry(mapping_id="MAP-051", trigger=RegulatoryTrigger.MULE_LIKE,
                 reference_id="FATF-INR10-P20", rationale=_NETWORK_RATIONALE),
    MappingEntry(mapping_id="MAP-052", trigger=RegulatoryTrigger.LAYERING,
                 reference_id="FATF-INR10-P20", rationale=_NETWORK_RATIONALE),
    MappingEntry(mapping_id="MAP-053", trigger=RegulatoryTrigger.STRUCTURING,
                 reference_id="FATF-INR10-P20", rationale=_NETWORK_RATIONALE),
    MappingEntry(mapping_id="MAP-054", trigger=RegulatoryTrigger.FAN_IN,
                 reference_id="FATF-INR10-P20", rationale=_NETWORK_RATIONALE),
    MappingEntry(mapping_id="MAP-055", trigger=RegulatoryTrigger.FAN_OUT,
                 reference_id="FATF-INR10-P20", rationale=_NETWORK_RATIONALE),
    MappingEntry(mapping_id="MAP-056", trigger=RegulatoryTrigger.RAPID_FORWARDING,
                 reference_id="FATF-INR10-P20", rationale=_NETWORK_RATIONALE),
    MappingEntry(mapping_id="MAP-057", trigger=RegulatoryTrigger.SUSPICIOUS_CLUSTER,
                 reference_id="FATF-INR10-P20", rationale=_NETWORK_RATIONALE),
    # NEW_DEVICE, NEW_BENEFICIARY, UNUSUAL_TIMING, LOCATION_ANOMALY:
    # intentionally unmapped — no approved source text found in the
    # repository's documents. Reported as unmapped triggers.
]


def _validate_registry() -> None:
    ids = [m.mapping_id for m in MAPPINGS]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate mapping_id in MAPPINGS")
    for m in MAPPINGS:
        if m.reference_id not in REFERENCES:
            raise ValueError(f"{m.mapping_id} references unknown {m.reference_id}")


_validate_registry()


def mappings_for(trigger: RegulatoryTrigger) -> list[MappingEntry]:
    """All mapping entries for a trigger (empty list = unmapped)."""
    return [m for m in MAPPINGS if m.trigger == trigger]


def get_reference(reference_id: str) -> Optional[RegulatoryReference]:
    return REFERENCES.get(reference_id)
