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

- [x] IEEE-CIS dataset available (`dataset/raw/ieee_cis/`)
- [x] PaySim dataset available (`dataset/raw/paysim/`)
- [x] Regulatory source material available (`dataset/raw/regulatory/fatf/` and `dataset/raw/regulatory/rbi/`)
- [x] Sanctions data available (`dataset/raw/sanctions/ofac/` and `dataset/raw/sanctions/un/`)
- [x] Dataset raw directories organized
- [ ] Custom Synthetic India Dataset (STATUS: TO BE GENERATED - generated programmatically later)

---

# 4. Groq API (LLM Provider)

- [ ] Groq account / Free API key obtained
- [ ] API key stored securely in `.env`
- [ ] API key NOT committed to Git
- [ ] Groq API model configured (e.g. `GROQ_MODEL`)
- [ ] Groq API connectivity tested

---

# 5. NewsAPI

- [ ] NewsAPI account created
- [ ] API key obtained
- [ ] API key stored securely in `.env`
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
- [ ] Connection string stored securely in `.env`
- [ ] Database connectivity tested

---

# 7. Neo4j / Neo4j Aura

- [ ] Neo4j account created
- [ ] Free development database created
- [ ] Database credentials obtained
- [ ] Connection URI obtained
- [ ] Credentials stored securely in `.env`
- [ ] Database connectivity tested

---

# 8. Mock Services

No external account is required for the following (simulated internal banking services):

- [ ] Mock Core Banking
- [ ] Mock KYC
- [ ] Mock Device Registry
- [ ] Mock Beneficiary Database
- [ ] Mock Geolocation
- [ ] Mock Transaction Alert Source

These will be implemented by the AI coding agent.

---

# 9. Sanctions Data

- [x] OFAC source data available (`dataset/raw/sanctions/ofac/ofac_sdn.csv`)
- [x] UN consolidated sanctions data available (`dataset/raw/sanctions/un/un_consolidated_sanctions.xml`)

---

# 10. Regulatory Sources

- [x] Official RBI source material available (`dataset/raw/regulatory/rbi/`)
- [x] FATF source material available (`dataset/raw/regulatory/fatf/`)
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