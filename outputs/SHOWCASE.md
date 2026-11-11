# ClaimGuard AI - Showcase: inputs and outputs

Engine: **langgraph**. Every sample was processed by the full multi-agent pipeline. Input documents are in `data/sample_claims/<CLAIM-ID>/`, outputs in `outputs/<CLAIM-ID>/`.

| Claim | Scenario (input) | Claimed | Fraud score | Band | Decision | Net payable |
|---|---|---:|---:|---|---|---:|
| CLM-2026-1001 | Genuine - Dengue fever at network hospital | ₹38,450 | 1.2 | LOW | AUTO_APPROVE | ₹37,950 |
| CLM-2026-1002 | Genuine - Laparoscopic appendectomy (room-rent above cap) | ₹1,28,300 | 0.8 | LOW | AUTO_APPROVE | ₹67,200 |
| CLM-2026-1003 | Suspicious - Typhoid, prolonged stay, repeat claimant at a spiking hospital | ₹56,050 | 49.4 | MEDIUM | HUMAN_REVIEW | ₹49,995 |
| CLM-2026-1004 | Fraud - Fever billed at Rs 1.2 lakh with MRI/CT/Endoscopy, edited bill | ₹1,20,000 | 97.5 | HIGH | SIU_INVESTIGATION | - |
| CLM-2026-1005 | Non-disclosure - Angioplasty 8 months after inception, undeclared diabetes & hypertension | ₹3,62,400 | 33.3 | MEDIUM | HUMAN_REVIEW | ₹3,61,900 |
| CLM-2026-1006 | Incomplete - Accident fracture, discharge summary missing, bill unsigned | ₹92,200 | - | - | PENDING_DOCUMENTS | - |
| CLM-2026-1007 | Duplicate - Same hospital bill already settled by another insurer | ₹27,850 | 74.0 | HIGH | SIU_INVESTIGATION | - |

## CLM-2026-1001 - Genuine - Dengue fever at network hospital

**Input documents:** claim_form.pdf, discharge_summary.pdf, hospital_bill.pdf, prescription.pdf  
**Designed to show:** LOW risk -> auto-approve

```text
Fraud Score: 1 (Low Risk - Genuine)
Suspicious Reasons:
- None
Triggered Categories:
- None
Decision: AUTO APPROVE
```

**Case note:** Claim CLM-2026-1001: Anil Kumar, Dengue Fever with Thrombocytopenia at Sunrise Multispeciality Hospital (4 day stay), claimed ₹38,450. Fraud score 1.2/100 (Genuine); rule engine 0.0, ML model 2.7. Categories triggered: none. Decision: AUTO APPROVE - Low fraud risk and admissible. Approve for settlement as computed.

**Settlement:**

- Amount claimed: ₹38,450
- Non-payable items (Registration & Admission charges): -₹500
- Net payable: ₹37,950

## CLM-2026-1002 - Genuine - Laparoscopic appendectomy (room-rent above cap)

**Input documents:** claim_form.pdf, discharge_summary.pdf, hospital_bill.pdf, prescription.pdf  
**Designed to show:** LOW risk -> approve with proportionate deduction

```text
Fraud Score: 1 (Low Risk - Genuine)
Suspicious Reasons:
- None
Triggered Categories:
- None
Decision: AUTO APPROVE
```

**Case note:** Claim CLM-2026-1002: Arjun Sharma, Acute Appendicitis at CityCare Super Speciality Hospital (3 day stay), claimed ₹1,28,300. Fraud score 0.8/100 (Genuine); rule engine 0.0, ML model 1.8. Categories triggered: none. Decision: AUTO APPROVE - Low fraud risk and admissible. Approve for settlement as computed.

**Settlement:**

- Amount claimed: ₹1,28,300
- Non-payable items (Registration & Admission charges): -₹500
- Proportionate deduction: room ₹7,500/day vs eligible ₹3,000/day (40% of associated charges ₹1,01,000 payable): -₹60,600
- Net payable: ₹67,200

## CLM-2026-1003 - Suspicious - Typhoid, prolonged stay, repeat claimant at a spiking hospital

**Input documents:** claim_form.pdf, discharge_summary.pdf, hospital_bill.pdf, prescription.pdf  
**Designed to show:** MEDIUM risk -> human review

```text
Fraud Score: 49 (Medium Risk - Suspicious)
Suspicious Reasons:
- 2 previous claims in the last 12 months, all at the same hospital (Greenvalley Hospital): 2026-03-02 Acute gastroenteritis ₹32,000, 2026-07-15 Viral fever ₹28,500
- Length of stay 7 days exceeds the typical 3-6 days for typhoid fever
- Clinical notes show recovery by day 4 but patient was kept 3 more day(s)
- Claim 40 days after sum insured was enhanced from ₹3,00,000 to ₹5,00,000 at renewal
- Provider risk index 0.38 for Greenvalley Hospital
- Claim volume from Greenvalley Hospital is 2.0x its 90-day baseline (96 vs 48)
Triggered Categories:
- Hospital Pattern Risk
- Treatment Duration Abnormality
- Patient Claim History
- Suspicious Timing (new policy)
Decision: HUMAN REVIEW
```

**Case note:** Claim CLM-2026-1003: Suresh Babu, Enteric (Typhoid) Fever at Greenvalley Hospital (7 day stay), claimed ₹56,050. Fraud score 49.4/100 (Suspicious); rule engine 71.4, ML model 22.5. Categories triggered: Hospital Pattern Risk, Treatment Duration Abnormality, Patient Claim History, Suspicious Timing (new policy). Key concerns: 2 previous claims in the last 12 months, all at the same hospital (Greenvalley Hospital): 2026-03-02 Acute gastroenteritis ₹32,000, 2026-07-15 Viral fever ₹28,500 | Length of stay 7 days exceeds the typical 3-6 days for typhoid fever | Clinical notes show recovery by day 4 but patient was kept 3 more day(s). Decision: HUMAN REVIEW - Route to a senior claims assessor / medical officer for manual review before settlement.

**Settlement:**

- Amount claimed: ₹56,050
- Non-payable items (Registration & Admission charges): -₹500
- Co-payment 10%: -₹5,555
- Net payable: ₹49,995

## CLM-2026-1004 - Fraud - Fever billed at Rs 1.2 lakh with MRI/CT/Endoscopy, edited bill

**Input documents:** claim_form.pdf, discharge_summary.pdf, hospital_bill.pdf  
**Designed to show:** HIGH risk -> SIU investigation

```text
Fraud Score: 98 (High Risk)
Suspicious Reasons:
- Possible document tampering in hospital_bill.pdf: PDF produced/edited with image-editing software ('photoshop'); PDF modified 5 day(s) after creation (28-Oct-2026 -> 02-Nov-2026)
- Bill does not tally: grand total ₹1,20,000 but line items add up to ₹1,23,300 (₹3,300 less than the items)
- Total bill ₹1,20,000 is 4.9x the typical maximum ₹24,500 for viral fever at a small clinic
- 5 item(s) charged above benchmark: Nursing charges ₹2,500 (benchmark <= ₹1,575); Physician consultation ₹2,000 (benchmark <= ₹1,750); MRI Brain (plain) ₹18,500 (benchmark <= ₹10,500); CT Scan Chest ₹9,500 (benchmark <= ₹6,125); Upper GI Endoscopy ₹12,400 (benchmark <= ₹7,875)
- Treatment does not match diagnosis: MRI Brain (plain), CT Scan Chest, Upper GI Endoscopy (₹40,400) not clinically indicated for viral fever
- Length of stay 5 days exceeds the typical 0-3 days for viral fever
- Hospitalised only 25 days after buying the policy (initial 30-day waiting period)
- Shree Sai Clinic & Nursing Home is on the fraud watchlist: 3 SIU-confirmed cases of inflated bills in 2025; diagnostics billed without an in-house MRI/CT facility.
- 12-bed clinic billing like a premium hospital (₹1,20,000; advanced diagnostics billed: MRI Brain (plain), CT Scan Chest, Upper GI Endoscopy)
- Hospital bill has no seal / authorised signature
- Treating doctor's medical council registration number is missing (Dr. R. Mahesh)
- Deluxe Room Rent at ₹9,000/day exceeds ₹7,000/day benchmark for a small clinic
Triggered Categories:
- Document Issues
- Hospital Pattern Risk
- Treatment Duration Abnormality
- Bill Amount
- Single Item Charge
- Diagnosis Mismatch
- Suspicious Timing (new policy)
- Room Rent / Procedure Overcharging
Decision: SIU INVESTIGATION
```

**Case note:** Claim CLM-2026-1004: Kiran Kumar, Pyrexia of unknown origin at Shree Sai Clinic & Nursing Home (5 day stay), claimed ₹1,20,000. Fraud score 97.5/100 (High Fraud Risk); rule engine 99.6, ML model 95.0. Categories triggered: Document Issues, Hospital Pattern Risk, Treatment Duration Abnormality, Bill Amount. Key concerns: Possible document tampering in hospital_bill.pdf: PDF produced/edited with image-editing software ('photoshop'); PDF modified 5 day(s) after creation (28-Oct-2026 -> 02-Nov-2026) | Bill does not tally: grand total ₹1,20,000 but line items add up to ₹1,23,300 (₹3,300 less than the items) | Total bill ₹1,20,000 is 4.9x the typical maximum ₹24,500 for viral fever at a small clinic. Decision: SIU INVESTIGATION - Hold payment. Refer to Special Investigation Unit (SIU) for field verification. Coverage issues: Initial waiting period: illness claim 25 days after inception (< 30 days)

**SIU case SIU-CLM-2026-1004** (P1 - Critical):

- Call the hospital to confirm admission, treating doctor and bill number
- Verify Dr. registration (not provided) with the State Medical Council
- Verify document authenticity with hospital records department; obtain original signed & sealed copies
- Field visit to hospital: verify bed count, ICU/diagnostic facilities, in-patient register for admission dates
- Check nursing notes & vitals charts for the full stay to confirm need for hospitalisation
- Obtain itemised indoor case papers and compare with treatment actually given
- Collect original pharmacy & diagnostic invoices; verify rates against hospital tariff card
- Medical officer to review clinical justification; obtain MRI/CT/endoscopy films and reports with timestamps
- Verify prior medical history with family physician / pharmacy records (pre-policy consultations)
- Reconcile room-days and charges with hospital admission/discharge register
- Interview patient / family on symptoms, admission and payments made
- Compare signatures on claim form, bill and discharge summary

## CLM-2026-1005 - Non-disclosure - Angioplasty 8 months after inception, undeclared diabetes & hypertension

**Input documents:** claim_form.pdf, discharge_summary.pdf, hospital_bill.pdf, prescription.pdf  
**Designed to show:** MEDIUM/HIGH risk -> review for misrepresentation

```text
Fraud Score: 33 (Medium Risk - Suspicious)
Suspicious Reasons:
- Discharge summary records diabetes, hypertension for 6 years, but none was declared at proposal; policy is only 245 days old (possible non-disclosure)
Triggered Categories:
- Suspicious Timing (new policy)
Decision: HUMAN REVIEW
```

**Case note:** Claim CLM-2026-1005: Lakshmi Prasad, Coronary Artery Disease - NSTEMI, Single vessel disease (LAD) at CityCare Super Speciality Hospital (4 day stay), claimed ₹3,62,400. Fraud score 33.3/100 (Suspicious); rule engine 43.0, ML model 21.5. Categories triggered: Suspicious Timing (new policy). Key concerns: Discharge summary records diabetes, hypertension for 6 years, but none was declared at proposal; policy is only 245 days old (possible non-disclosure). Decision: HUMAN REVIEW - Route to a senior claims assessor / medical officer for manual review before settlement. Coverage issues: Undeclared pre-existing condition(s) (diabetes, hypertension) within 36-month PED window - refer to underwriting

**Settlement:**

- Amount claimed: ₹3,62,400
- Non-payable items (Registration & Admission charges): -₹500
- Net payable: ₹3,61,900

## CLM-2026-1006 - Incomplete - Accident fracture, discharge summary missing, bill unsigned

**Input documents:** claim_form.pdf, hospital_bill.pdf  
**Designed to show:** Pending documents (claim paused)

```text
Status: PENDING DOCUMENTS
Required:
- Discharge summary signed by the treating doctor
- Re-submit: Hospital bill has no seal / authorised signature
```

**Case note:** Claim CLM-2026-1006 for Rahul Verma at Apex Ortho & Trauma Centre cannot be assessed yet: 2 required item(s) are missing. The claim has been paused and a deficiency letter drafted. Fraud scoring will run automatically once documents are received.

**Documents requested:**

- Discharge summary signed by the treating doctor
- Re-submit: Hospital bill has no seal / authorised signature

## CLM-2026-1007 - Duplicate - Same hospital bill already settled by another insurer

**Input documents:** claim_form.pdf, discharge_summary.pdf, hospital_bill.pdf  
**Designed to show:** HIGH risk -> SIU (duplicate billing)

```text
Fraud Score: 74 (High Risk)
Suspicious Reasons:
- Duplicate claim: hospital bill SMC/IP/2026/08812 was already claimed with Other Insurer (simulated registry) (policy OTH-HL-77821) on 2026-10-20 for ₹27,850 - status SETTLED - FULL AMOUNT
- Claim form declares no other health policy, but the industry registry shows another active policy
Triggered Categories:
- Patient Claim History
Decision: SIU INVESTIGATION
```

**Case note:** Claim CLM-2026-1007: Priya Nair, Acute Gastroenteritis with moderate dehydration at Seaside Medical Centre (2 day stay), claimed ₹27,850. Fraud score 74.0/100 (High Fraud Risk); rule engine 80.0, ML model 55.8. Categories triggered: Patient Claim History. Key concerns: Duplicate claim: hospital bill SMC/IP/2026/08812 was already claimed with Other Insurer (simulated registry) (policy OTH-HL-77821) on 2026-10-20 for ₹27,850 - status SETTLED - FULL AMOUNT | Claim form declares no other health policy, but the industry registry shows another active policy. Decision: SIU INVESTIGATION - Hold payment. Refer to Special Investigation Unit (SIU) for field verification.

**SIU case SIU-CLM-2026-1007** (P1 - Critical):

- Call the hospital to confirm admission, treating doctor and bill number
- Verify Dr. registration (TCMC/2011/39004) with the State Medical Council
- Cross-check previous claims and industry registry; request settlement letter from other insurer
- Interview patient / family on symptoms, admission and payments made
- Compare signatures on claim form, bill and discharge summary
