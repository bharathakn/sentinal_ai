# Sentinel AI — Regulatory Source Control

## 1. Purpose

Sentinel AI uses regulatory information as part of its risk assessment and explanation workflow.

Regulatory information must be treated as controlled knowledge.

AI agents must not invent regulatory requirements, section numbers, thresholds, or typologies.

---

# 2. Regulatory Sources

Potential authoritative sources include:

- RBI
- FIU-IND
- FATF
- UN Security Council
- Other officially approved regulatory sources

---

# 3. Source Authority

Regulatory claims should preferably originate from authoritative source documents.

Secondary websites may help locate information but should not automatically become the authoritative source.

---

# 4. Regulatory Mapping

When Sentinel maps a detected pattern to a regulatory reference, the mapping must have an identifiable source.

Each mapping should record:

- Internal pattern name
- Regulatory organization
- Document name
- Section or reference
- Relevant text/context
- Source date/version
- Verification status

---

# 5. AI Restrictions

AI agents must not independently create regulatory mappings.

For example, an agent must not decide that:

"layering = regulatory section X"

unless that mapping has been previously approved and recorded.

If a regulatory mapping is missing:

The agent must report the missing mapping instead of inventing one.

---

# 6. Risk Score Rules

Risk scoring logic must be deterministic and reviewable.

The LLM must not independently change:

- Risk weights
- Risk thresholds
- Recommended actions
- Regulatory mappings

These belong to controlled application logic.

---

# 7. Recommended Actions

Actions such as:

- Clear
- Monitor
- Escalate
- Block
- Human review

must be generated from explicitly defined application rules.

The LLM may explain the resulting action but must not secretly change the decision logic.

---

# 8. SAR / Regulatory Filing

A prototype recommendation must not be presented as an actual regulatory filing.

Any statement suggesting filing or escalation must be clearly treated as a system recommendation requiring qualified human review.

---

# 9. Version Control

Changes to regulatory mappings must be versioned.

A change should record:

- Previous mapping
- New mapping
- Reason for change
- Source
- Reviewer/approver
- Date

---

# 10. Human Review

Regulatory information should remain subject to human review.

Sentinel AI is an investigation-assistance prototype and not an autonomous regulatory decision-maker.

---

# 11. Important Accuracy Rule

Project documentation may contain proposed regulatory references or example mappings.

These must not automatically be treated as verified regulatory facts.

Before final implementation or presentation:

- Verify the source.
- Verify the section.
- Verify the wording.
- Verify the applicability.
- Record the verified source.

---

# 12. Agent Rule

If the agent cannot verify a regulatory claim from the project's approved regulatory sources:

It must not fabricate the answer.

It should mark the item as requiring verification.