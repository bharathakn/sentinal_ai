# Sentinel AI — Manual Setup Checklist

## 1. Purpose

This checklist contains tasks that must be completed manually by the project owner.

AI coding agents may guide the developer but must not assume that these tasks have been completed.

---

# 2. Project Environment

- [ ] Project directory created
- [ ] Git initialized
- [ ] GitHub repository created
- [ ] Initial project documentation committed
- [ ] Python environment prepared
- [ ] Node.js environment prepared
- [ ] IDE configured
- [ ] AI coding agent configured

---

# 3. Datasets

- [x] IEEE-CIS dataset downloaded
- [x] PaySim dataset downloaded
- [ ] Dataset raw directories organized
- [ ] Dataset integrity verified
- [ ] Dataset provenance documented
- [ ] Custom Synthetic India Dataset generated later

---

# 4. Anthropic / Claude

- [ ] Anthropic account available
- [ ] API access enabled
- [ ] API key created
- [ ] API key stored securely
- [ ] API key NOT committed to Git
- [ ] Claude API connectivity tested

---

# 5. NewsAPI

- [ ] NewsAPI account created
- [ ] API key obtained
- [ ] API key stored securely
- [ ] API key NOT committed to Git
- [ ] NewsAPI connectivity tested

---

# 6. MongoDB Atlas

- [ ] MongoDB Atlas account created
- [ ] Sentinel project created
- [ ] Free development cluster created
- [ ] Database user created
- [ ] Network access configured
- [ ] Connection string obtained
- [ ] Connection string stored securely
- [ ] Database connectivity tested

---

# 7. Neo4j Aura

- [ ] Neo4j account created
- [ ] Free development database created
- [ ] Database credentials obtained
- [ ] Connection URI obtained
- [ ] Credentials stored securely
- [ ] Database connectivity tested

---

# 8. Mock Services

No external account is required for the following:

- [ ] Mock Core Banking
- [ ] Mock KYC
- [ ] Mock Device Registry
- [ ] Mock Beneficiary Database
- [ ] Mock Geolocation
- [ ] Mock Transaction Alert Source

These will be implemented by the AI coding agent.

---

# 9. Sanctions Data

- [ ] OFAC source identified
- [ ] OFAC data availability verified
- [ ] UN consolidated sanctions source identified
- [ ] UN data availability verified

---

# 10. Regulatory Sources

- [ ] Official RBI sources identified
- [ ] Relevant RBI AML material verified
- [ ] FIU-IND material verified where applicable
- [ ] FATF source material identified
- [ ] Regulatory mappings approved before implementation

---

# 11. Security

- [ ] Secrets excluded from Git
- [ ] Environment configuration excluded where necessary
- [ ] `.gitignore` reviewed
- [ ] No API keys in source code
- [ ] No API keys in Markdown
- [ ] No credentials in screenshots
- [ ] No real customer data used

---

# 12. Final Pre-Coding Check

Before asking an AI agent to implement the full pipeline:

- [ ] Dataset locations confirmed
- [ ] Dataset schemas inspected
- [ ] Required credentials available
- [ ] MongoDB available
- [ ] Neo4j available
- [ ] Mock API architecture approved
- [ ] Regulatory sources verified
- [ ] Git clean
- [ ] Initial commit created

---

# 13. Important Rule

An unchecked item must not be silently assumed to be complete.

If an agent encounters a missing manual setup requirement:

1. Identify the missing requirement.
2. Explain why it is required.
3. Do not expose or request secret values in the chat.
4. Continue only if a safe mock/test path exists.