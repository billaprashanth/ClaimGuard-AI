"""Generate the 7 showcase claim packages as realistic PDF documents.

Every document is SYNTHETIC (fictional people, hospitals and policies) and carries
a footer saying so. Run:  python scripts/generate_sample_claims.py
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.tools.knowledge_base import hospitals  # noqa: E402

OUT = ROOT / "data" / "sample_claims"
W, H = A4
FOOT = "SYNTHETIC SAMPLE DOCUMENT - generated for ClaimGuard AI testing. Fictional persons & hospitals. Not a real record."
HOSP = {h["hospital_id"]: h for h in hospitals()}


def money(x: float) -> str:
    s = f"{x:,.2f}"
    # Indian grouping for readability on the documents
    whole, dec = s.split(".")
    n = whole.replace(",", "")
    if len(n) > 3:
        head, tail = n[:-3], n[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        n = ",".join(parts + [tail])
    return f"{n}.{dec}"


# --------------------------------------------------------------------------- scenarios
SCENARIOS = [
    {
        "id": "CLM-2026-1001",
        "title": "Genuine - Dengue fever at network hospital",
        "expected": "LOW risk -> auto-approve",
        "hospital": "HSP-TG-0101",
        "claim_form": {
            "Claim Reference": "CLM-2026-1001", "Policy Number": "POL-HS-240011", "Proposer Name": "Anil Kumar",
            "Patient Name": "Anil Kumar", "Date of Birth": "11-02-1984", "Age": "42", "Gender": "Male",
            "Relationship with Proposer": "Self", "Hospital Name": "Sunrise Multispeciality Hospital, Hyderabad",
            "Date of Admission": "14-10-2026", "Date of Discharge": "18-10-2026", "Diagnosis": "Dengue Fever",
            "Injury due to Accident": "No", "Claim Type": "Reimbursement", "Total Amount Claimed": "Rs. 38,450.00",
            "Other Active Health Policies": "None", "Date of Submission": "24-10-2026",
        },
        "bill": {
            "Bill No": "SMH/IP/2026/10342", "Bill Date": "18-10-2026", "IP No": "IP-26-55821",
            "Patient Name": "Anil Kumar", "Age": "42", "Date of Admission": "14-10-2026",
            "Date of Discharge": "18-10-2026", "Room Category": "Semi Private",
        },
        "items": [
            ("Registration & Admission charges", "MISC", 1, 500),
            ("Semi Private Room Rent", "ROOM", 4, 4000),
            ("Nursing charges", "NURSING", 4, 900),
            ("Physician consultation", "CONSULT", 5, 800),
            ("Dengue NS1 Antigen & IgM", "LAB", 1, 1400),
            ("Complete Blood Count (CBC)", "LAB", 4, 350),
            ("Platelet count (serial)", "LAB", 6, 250),
            ("Liver Function Test (LFT)", "LAB", 1, 900),
            ("Ultrasound Abdomen", "RADIOLOGY", 1, 1800),
            ("IV Fluids - Normal Saline", "PHARMACY", 12, 120),
            ("Pharmacy - medicines", "PHARMACY", 1, 4910),
            ("Medical consumables", "CONSUMABLE", 1, 1000),
        ],
        "discharge": {
            "Patient Name": "Anil Kumar", "Age": "42", "Gender": "Male", "IP No": "IP-26-55821",
            "Date of Admission": "14-10-2026", "Date of Discharge": "18-10-2026",
            "Final Diagnosis": "Dengue Fever with Thrombocytopenia", "ICD-10 Code": "A90",
            "Treating Doctor": "Dr. Srinivas Rao, MD (General Medicine)", "Doctor Registration No": "TSMC/2009/14522",
            "Procedures Performed": "None (conservative management)",
            "Past History": "No known comorbidities. Not a known case of diabetes or hypertension.",
            "Course in Hospital": "Patient presented with high grade fever for 3 days, myalgia and headache. NS1 antigen positive. Platelet count dropped to 62,000 on day 2 and recovered to 1,45,000 with IV fluids and supportive care. No bleeding manifestations.",
            "Condition at Discharge": "Stable, afebrile. Platelets 1,45,000.",
        },
        "prescription": ["Tab. Paracetamol 650 mg - 1-1-1 x 3 days (SOS for fever)", "ORS sachets - as advised", "Review CBC after 5 days"],
    },
    {
        "id": "CLM-2026-1002",
        "title": "Genuine - Laparoscopic appendectomy (room-rent above cap)",
        "expected": "LOW risk -> approve with proportionate deduction",
        "hospital": "HSP-KA-0207",
        "claim_form": {
            "Claim Reference": "CLM-2026-1002", "Policy Number": "POL-HS-220457", "Proposer Name": "Meena Sharma",
            "Patient Name": "Arjun Sharma", "Date of Birth": "19-05-2007", "Age": "19", "Gender": "Male",
            "Relationship with Proposer": "Son", "Hospital Name": "CityCare Super Speciality Hospital, Bengaluru",
            "Date of Admission": "05-10-2026", "Date of Discharge": "08-10-2026", "Diagnosis": "Acute Appendicitis",
            "Injury due to Accident": "No", "Claim Type": "Cashless", "Total Amount Claimed": "Rs. 1,28,300.00",
            "Other Active Health Policies": "None", "Date of Submission": "08-10-2026",
        },
        "bill": {
            "Bill No": "CCSH/IP/2026/33107", "Bill Date": "08-10-2026", "IP No": "CC-IP-901244",
            "Patient Name": "Arjun Sharma", "Age": "19", "Date of Admission": "05-10-2026",
            "Date of Discharge": "08-10-2026", "Room Category": "Private",
        },
        "items": [
            ("Registration & Admission charges", "MISC", 1, 500),
            ("Private Room Rent", "ROOM", 3, 7500),
            ("Nursing charges", "NURSING", 3, 1500),
            ("Surgeon consultation / visits", "CONSULT", 4, 1500),
            ("Complete Blood Count (CBC)", "LAB", 1, 600),
            ("Ultrasound Abdomen", "RADIOLOGY", 1, 2800),
            ("CT Scan Abdomen (contrast)", "RADIOLOGY", 1, 6500),
            ("Laparoscopic Appendectomy - Surgeon fee", "PROCEDURE", 1, 38000),
            ("OT charges", "OT", 1, 18000),
            ("Anaesthesia charges", "PROCEDURE", 1, 12000),
            ("Pharmacy - medicines", "PHARMACY", 1, 9800),
            ("Surgical consumables", "CONSUMABLE", 1, 5600),
            ("Histopathology - appendix specimen", "LAB", 1, 1500),
        ],
        "discharge": {
            "Patient Name": "Arjun Sharma", "Age": "19", "Gender": "Male", "IP No": "CC-IP-901244",
            "Date of Admission": "05-10-2026", "Date of Discharge": "08-10-2026",
            "Final Diagnosis": "Acute Appendicitis", "ICD-10 Code": "K35.80",
            "Treating Doctor": "Dr. Kavitha Menon, MS (General Surgery)", "Doctor Registration No": "KMC/2012/88341",
            "Procedures Performed": "Laparoscopic Appendectomy under GA on 05-10-2026",
            "Past History": "Nil significant.",
            "Course in Hospital": "Presented with right iliac fossa pain, fever and vomiting for 1 day. USG and CECT abdomen confirmed acute appendicitis. Underwent laparoscopic appendectomy. Post-operative period uneventful. Specimen sent for histopathology.",
            "Condition at Discharge": "Stable. Wound healthy.",
        },
        "prescription": ["Tab. Cefuroxime 500 mg - 1-0-1 x 5 days", "Tab. Paracetamol 650 mg - SOS", "Suture removal on day 7"],
    },
    {
        "id": "CLM-2026-1003",
        "title": "Suspicious - Typhoid, prolonged stay, repeat claimant at a spiking hospital",
        "expected": "MEDIUM risk -> human review",
        "hospital": "HSP-TG-0333",
        "claim_form": {
            "Claim Reference": "CLM-2026-1003", "Policy Number": "POL-HS-250789", "Proposer Name": "Suresh Babu",
            "Patient Name": "Suresh Babu", "Date of Birth": "08-03-1975", "Age": "51", "Gender": "Male",
            "Relationship with Proposer": "Self", "Hospital Name": "Greenvalley Hospital, Warangal",
            "Date of Admission": "20-10-2026", "Date of Discharge": "27-10-2026", "Diagnosis": "Typhoid Fever",
            "Injury due to Accident": "No", "Claim Type": "Reimbursement", "Total Amount Claimed": "Rs. 56,050.00",
            "Other Active Health Policies": "None", "Date of Submission": "03-11-2026",
        },
        "bill": {
            "Bill No": "GVH/2026/4471", "Bill Date": "27-10-2026", "IP No": "GV-2026-1188",
            "Patient Name": "Suresh Babu", "Age": "51", "Date of Admission": "20-10-2026",
            "Date of Discharge": "27-10-2026", "Room Category": "Private",
        },
        "items": [
            ("Registration & Admission charges", "MISC", 1, 500),
            ("Private Room Rent", "ROOM", 7, 4000),
            ("Nursing charges", "NURSING", 7, 800),
            ("Physician consultation", "CONSULT", 8, 800),
            ("Widal test", "LAB", 1, 450),
            ("Typhidot IgM", "LAB", 1, 900),
            ("Blood culture & sensitivity", "LAB", 1, 1600),
            ("Complete Blood Count (CBC)", "LAB", 3, 400),
            ("Liver Function Test (LFT)", "LAB", 1, 900),
            ("Ultrasound Abdomen", "RADIOLOGY", 1, 2200),
            ("Inj. Ceftriaxone 1g", "PHARMACY", 14, 250),
            ("Pharmacy - medicines", "PHARMACY", 1, 3800),
            ("Medical consumables", "CONSUMABLE", 1, 1000),
        ],
        "discharge": {
            "Patient Name": "Suresh Babu", "Age": "51", "Gender": "Male", "IP No": "GV-2026-1188",
            "Date of Admission": "20-10-2026", "Date of Discharge": "27-10-2026",
            "Final Diagnosis": "Enteric (Typhoid) Fever", "ICD-10 Code": "A01.0",
            "Treating Doctor": "Dr. P. Venkatesh, MD", "Doctor Registration No": "TSMC/2014/20377",
            "Procedures Performed": "None",
            "Past History": "Not significant.",
            "Course in Hospital": "Admitted with fever for 6 days and abdominal discomfort. Typhidot IgM positive. Treated with IV ceftriaxone. Fever subsided on day 4. Patient kept under observation for general weakness and discharged on day 7.",
            "Condition at Discharge": "Afebrile, ambulant.",
        },
        "prescription": ["Tab. Azithromycin 500 mg - 1-0-0 x 5 days", "Tab. Pantoprazole 40 mg - 1-0-0 x 7 days"],
    },
    {
        "id": "CLM-2026-1004",
        "title": "Fraud - Fever billed at Rs 1.2 lakh with MRI/CT/Endoscopy, edited bill",
        "expected": "HIGH risk -> SIU investigation",
        "hospital": "HSP-TG-0450",
        "claim_form": {
            "Claim Reference": "CLM-2026-1004", "Policy Number": "POL-HS-260921", "Proposer Name": "Kiran Kumar",
            "Patient Name": "Kiran Kumar", "Date of Birth": "02-08-1992", "Age": "34", "Gender": "Male",
            "Relationship with Proposer": "Self", "Hospital Name": "Shree Sai Clinic & Nursing Home, Karimnagar",
            "Date of Admission": "23-10-2026", "Date of Discharge": "28-10-2026", "Diagnosis": "Viral Fever",
            "Injury due to Accident": "No", "Claim Type": "Reimbursement", "Total Amount Claimed": "Rs. 1,20,000.00",
            "Other Active Health Policies": "None", "Date of Submission": "02-11-2026",
        },
        "bill": {
            "Bill No": "SSC/2026/0981", "Bill Date": "28-10-2026", "IP No": "SS-0981",
            "Patient Name": "Kiran Kumar", "Age": "34", "Date of Admission": "23-10-2026",
            "Date of Discharge": "28-10-2026", "Room Category": "Deluxe",
        },
        "items": [
            ("Deluxe Room Rent", "ROOM", 5, 9000),
            ("Nursing charges", "NURSING", 5, 2500),
            ("Physician consultation", "CONSULT", 10, 2000),
            ("MRI Brain (plain)", "RADIOLOGY", 1, 18500),
            ("CT Scan Chest", "RADIOLOGY", 1, 9500),
            ("Upper GI Endoscopy", "PROCEDURE", 1, 12400),
            ("Complete Blood Count (CBC)", "LAB", 1, 600),
            ("Complete Blood Count (CBC)", "LAB", 1, 600),
            ("Pharmacy - medicines", "PHARMACY", 1, 4200),
        ],
        "bill_total_override": 120000,
        "seal": False,
        "tamper": "Adobe Photoshop 25.0 (Windows)",
        "discharge": {
            "Patient Name": "Kiran Kumar P", "Age": "34", "Gender": "Male", "IP No": "SS-0981",
            "Date of Admission": "23-10-2026", "Date of Discharge": "28-10-2026",
            "Final Diagnosis": "Pyrexia of unknown origin", "ICD-10 Code": "R50.9",
            "Treating Doctor": "Dr. R. Mahesh", "Doctor Registration No": "",
            "Procedures Performed": "None",
            "Past History": "Nil.",
            "Course in Hospital": "Patient admitted with fever and body pains for 2 days. Treated symptomatically with antipyretics. Fever settled within 24 hours. Discharged in stable condition.",
            "Condition at Discharge": "Stable.",
        },
    },
    {
        "id": "CLM-2026-1005",
        "title": "Non-disclosure - Angioplasty 8 months after inception, undeclared diabetes & hypertension",
        "expected": "MEDIUM/HIGH risk -> review for misrepresentation",
        "hospital": "HSP-KA-0207",
        "claim_form": {
            "Claim Reference": "CLM-2026-1005", "Policy Number": "POL-HS-260145", "Proposer Name": "Lakshmi Prasad",
            "Patient Name": "Lakshmi Prasad", "Date of Birth": "14-06-1968", "Age": "58", "Gender": "Male",
            "Relationship with Proposer": "Self", "Hospital Name": "CityCare Super Speciality Hospital, Bengaluru",
            "Date of Admission": "01-11-2026", "Date of Discharge": "05-11-2026", "Diagnosis": "Coronary Artery Disease - NSTEMI",
            "Injury due to Accident": "No", "Claim Type": "Cashless", "Total Amount Claimed": "Rs. 3,62,400.00",
            "Other Active Health Policies": "None", "Pre-existing Disease Declared": "No", "Date of Submission": "05-11-2026",
        },
        "bill": {
            "Bill No": "CCSH/IP/2026/35920", "Bill Date": "05-11-2026", "IP No": "CC-IP-903871",
            "Patient Name": "Lakshmi Prasad", "Age": "58", "Date of Admission": "01-11-2026",
            "Date of Discharge": "05-11-2026", "Room Category": "Private",
        },
        "items": [
            ("Registration & Admission charges", "MISC", 1, 500),
            ("CCU / ICU charges", "ICU", 2, 22000),
            ("Private Room Rent", "ROOM", 2, 9000),
            ("Nursing charges", "NURSING", 4, 1800),
            ("Cardiologist consultation", "CONSULT", 8, 2000),
            ("ECG", "LAB", 3, 600),
            ("2D Echo", "RADIOLOGY", 1, 3200),
            ("Troponin I", "LAB", 2, 1500),
            ("Coronary Angiography", "PROCEDURE", 1, 22000),
            ("PTCA - Angioplasty procedure", "PROCEDURE", 1, 110000),
            ("Drug Eluting Stent", "IMPLANT", 1, 36000),
            ("Cath lab charges", "OT", 1, 45000),
            ("Pharmacy - medicines", "PHARMACY", 1, 38700),
            ("Cath lab consumables", "CONSUMABLE", 1, 17000),
        ],
        "discharge": {
            "Patient Name": "Lakshmi Prasad", "Age": "58", "Gender": "Male", "IP No": "CC-IP-903871",
            "Date of Admission": "01-11-2026", "Date of Discharge": "05-11-2026",
            "Final Diagnosis": "Coronary Artery Disease - NSTEMI, Single vessel disease (LAD)", "ICD-10 Code": "I25.10",
            "Treating Doctor": "Dr. Harish Gowda, DM (Cardiology)", "Doctor Registration No": "KMC/2006/51290",
            "Procedures Performed": "Coronary angiography + PTCA with 1 DES to LAD on 02-11-2026",
            "Past History": "Known case of Type 2 Diabetes Mellitus and Hypertension for the past 6 years, on regular medication (Metformin 500 mg BD, Telmisartan 40 mg OD).",
            "Course in Hospital": "Presented with chest pain and sweating. ECG showed ST depression, Troponin I elevated. Coronary angiography revealed 90% LAD stenosis; PTCA with DES done. Observed in CCU for 48 hours. Uneventful recovery.",
            "Condition at Discharge": "Haemodynamically stable.",
        },
        "prescription": ["Tab. Aspirin 75 mg - 0-1-0", "Tab. Ticagrelor 90 mg - 1-0-1", "Tab. Atorvastatin 80 mg - 0-0-1", "Tab. Metformin 500 mg - 1-0-1 (continue)", "Tab. Telmisartan 40 mg - 1-0-0 (continue)"],
    },
    {
        "id": "CLM-2026-1006",
        "title": "Incomplete - Accident fracture, discharge summary missing, bill unsigned",
        "expected": "Pending documents (claim paused)",
        "hospital": "HSP-TG-0512",
        "claim_form": {
            "Claim Reference": "CLM-2026-1006", "Policy Number": "POL-HS-230612", "Proposer Name": "Rahul Verma",
            "Patient Name": "Rahul Verma", "Date of Birth": "03-11-1997", "Age": "29", "Gender": "Male",
            "Relationship with Proposer": "Self", "Hospital Name": "Apex Ortho & Trauma Centre, Hyderabad",
            "Date of Admission": "30-10-2026", "Date of Discharge": "01-11-2026", "Diagnosis": "Fracture of right distal radius (road traffic accident)",
            "Injury due to Accident": "Yes", "Claim Type": "Reimbursement", "Total Amount Claimed": "Rs. 92,200.00",
            "Other Active Health Policies": "None", "Date of Submission": "06-11-2026",
        },
        "bill": {
            "Bill No": "AOTC/2026/7712", "Bill Date": "01-11-2026", "IP No": "AO-7712",
            "Patient Name": "Rahul Verma", "Age": "29", "Date of Admission": "30-10-2026",
            "Date of Discharge": "01-11-2026", "Room Category": "Semi Private",
        },
        "items": [
            ("Registration & Admission charges", "MISC", 1, 500),
            ("Semi Private Room Rent", "ROOM", 2, 3800),
            ("Nursing charges", "NURSING", 2, 1000),
            ("Orthopaedic consultation", "CONSULT", 3, 1200),
            ("X-Ray Right Wrist AP/Lateral", "RADIOLOGY", 2, 650),
            ("ORIF with plating - Surgeon fee", "PROCEDURE", 1, 30000),
            ("OT charges", "OT", 1, 15000),
            ("Anaesthesia charges", "PROCEDURE", 1, 9000),
            ("Locking plate & screws (implant)", "IMPLANT", 1, 14500),
            ("Pharmacy - medicines", "PHARMACY", 1, 6200),
            ("Surgical consumables", "CONSUMABLE", 1, 2500),
        ],
        "seal": False,
        "skip": ["discharge_summary"],
    },
    {
        "id": "CLM-2026-1007",
        "title": "Duplicate - Same hospital bill already settled by another insurer",
        "expected": "HIGH risk -> SIU (duplicate billing)",
        "hospital": "HSP-KL-0120",
        "claim_form": {
            "Claim Reference": "CLM-2026-1007", "Policy Number": "POL-HS-240330", "Proposer Name": "Priya Nair",
            "Patient Name": "Priya Nair", "Date of Birth": "14-05-1990", "Age": "36", "Gender": "Female",
            "Relationship with Proposer": "Self", "Hospital Name": "Seaside Medical Centre, Kochi",
            "Date of Admission": "09-10-2026", "Date of Discharge": "11-10-2026", "Diagnosis": "Acute Gastroenteritis",
            "Injury due to Accident": "No", "Claim Type": "Reimbursement", "Total Amount Claimed": "Rs. 27,850.00",
            "Other Active Health Policies": "None", "Date of Submission": "05-11-2026",
        },
        "bill": {
            "Bill No": "SMC/IP/2026/08812", "Bill Date": "11-10-2026", "IP No": "SMC-IP-44190",
            "Patient Name": "Priya Nair", "Age": "36", "Date of Admission": "09-10-2026",
            "Date of Discharge": "11-10-2026", "Room Category": "Semi Private",
        },
        "items": [
            ("Registration & Admission charges", "MISC", 1, 250),
            ("Semi Private Room Rent", "ROOM", 2, 3500),
            ("Nursing charges", "NURSING", 2, 900),
            ("Physician consultation", "CONSULT", 3, 900),
            ("Complete Blood Count (CBC)", "LAB", 1, 450),
            ("Serum Electrolytes", "LAB", 2, 750),
            ("Stool routine examination", "LAB", 1, 300),
            ("Renal Function Test (KFT)", "LAB", 1, 950),
            ("IV Fluids - Ringer Lactate", "PHARMACY", 10, 130),
            ("Inj. Ondansetron / antibiotics", "PHARMACY", 1, 3200),
            ("Pharmacy - medicines", "PHARMACY", 1, 6700),
            ("Ultrasound Abdomen", "RADIOLOGY", 1, 1700),
        ],
        "discharge": {
            "Patient Name": "Priya Nair", "Age": "36", "Gender": "Female", "IP No": "SMC-IP-44190",
            "Date of Admission": "09-10-2026", "Date of Discharge": "11-10-2026",
            "Final Diagnosis": "Acute Gastroenteritis with moderate dehydration", "ICD-10 Code": "A09",
            "Treating Doctor": "Dr. Anitha Thomas, MD", "Doctor Registration No": "TCMC/2011/39004",
            "Procedures Performed": "None",
            "Past History": "Nil.",
            "Course in Hospital": "Admitted with multiple episodes of loose stools and vomiting with moderate dehydration. Managed with IV fluids, antiemetics and antibiotics. Improved and discharged on day 2.",
            "Condition at Discharge": "Stable, tolerating orally.",
        },
    },
]


# --------------------------------------------------------------------------- drawing helpers
def _footer(c):
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(colors.grey)
    c.drawCentredString(W / 2, 22, FOOT)
    c.setFillColor(colors.black)


def _hospital_header(c, h, title):
    c.setFillColor(colors.HexColor("#0B4F6C"))
    c.rect(0, H - 92, W, 92, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(40, H - 40, h["name"])
    c.setFont("Helvetica", 9)
    c.drawString(40, H - 56, f"{h['city']}, {h['state']}   |   {h['beds']} beds   |   Ph: 040-{sum(map(ord, h['name'])) * 7919 % 10**8:08d}")
    c.drawString(40, H - 70, f"Hospital Registration No: {h['registration_no']}")
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(W / 2, H - 118, title)
    return H - 145


def _kv(c, y, pairs, x=40, size=10, gap=15):
    for k, v in pairs.items():
        c.setFont("Helvetica-Bold", size)
        c.drawString(x, y, f"{k}:")
        c.setFont("Helvetica", size)
        c.drawString(x + c.stringWidth(f"{k}: ", "Helvetica-Bold", size), y, str(v))
        y -= gap
    return y


def _para(c, y, label, text, width=95):
    import textwrap

    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, f"{label}:")
    y -= 14
    c.setFont("Helvetica", 10)
    for line in textwrap.wrap(text, width):
        c.drawString(40, y, line)
        y -= 13
    return y - 12


def _seal(c, y, present, signer):
    if present:
        c.setStrokeColor(colors.HexColor("#5B2A86"))
        c.setLineWidth(1.5)
        c.circle(W - 110, y + 5, 32)
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(colors.HexColor("#5B2A86"))
        c.drawCentredString(W - 110, y + 8, "HOSPITAL")
        c.drawCentredString(W - 110, y - 1, "SEAL")
        c.setFillColor(colors.black)
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Hospital Seal & Signature: ")
    c.setFont("Helvetica", 10)
    c.drawString(178, y, f"Present ({signer})" if present else "Not available")


def make_claim_form(path, s):
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"Claim Form {s['id']}")
    c.setCreator("ClaimGuard Insurer Portal")
    c.setFillColor(colors.HexColor("#1D3557"))
    c.rect(0, H - 80, W, 80, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, H - 42, "HEALTH INSURANCE CLAIM FORM")
    c.setFont("Helvetica", 9)
    c.drawString(40, H - 58, "Part A - To be filled in by the Insured  |  Demo Health Insurance Co. (fictional)")
    c.setFillColor(colors.black)
    y = _kv(c, H - 115, s["claim_form"], gap=19, size=10.5)
    y -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Declaration by the Insured:")
    c.setFont("Helvetica", 9)
    c.drawString(40, y - 14, "I hereby declare that the information furnished in this claim form is true & correct to the best of my knowledge.")
    c.drawString(40, y - 40, f"Signature of Insured: {s['claim_form']['Proposer Name']}  (e-signed)")
    _footer(c)
    c.save()


def make_bill(path, s):
    h = HOSP[s["hospital"]]
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"Final Bill {s['bill']['Bill No']}")
    c.setCreator("HIMS Billing Module v7.2")
    y = _hospital_header(c, h, "FINAL HOSPITAL BILL (IN-PATIENT)")
    y = _kv(c, y, s["bill"], gap=15)
    y -= 8
    cols = [40, 70, 330, 410, 445, 555]
    c.setFillColor(colors.HexColor("#E8F1F5"))
    c.rect(36, y - 5, W - 72, 18, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    for x, t in zip(cols[:3], ["S.No", "Particulars", "Category"]):
        c.drawString(x, y, t)
    c.drawRightString(cols[3] + 20, y, "Qty")
    c.drawRightString(cols[4] + 50, y, "Rate")
    c.drawRightString(cols[5], y, "Amount")
    y -= 20
    c.setFont("Helvetica", 9)
    total = 0
    for i, (desc, cat, qty, rate) in enumerate(s["items"], 1):
        amt = qty * rate
        total += amt
        c.drawString(cols[0], y, str(i))
        c.drawString(cols[1], y, desc)
        c.drawString(cols[2], y, cat)
        c.drawRightString(cols[3] + 20, y, str(qty))
        c.drawRightString(cols[4] + 50, y, money(rate))
        c.drawRightString(cols[5], y, money(amt))
        y -= 15
    c.line(36, y + 6, W - 36, y + 6)
    y -= 12
    grand = s.get("bill_total_override", total)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(330, y, "Grand Total:")
    c.drawRightString(cols[5], y, money(grand))
    c.setFont("Helvetica-Bold", 11)
    y -= 50
    _seal(c, y, s.get("seal", True), "Billing Manager")
    _footer(c)
    c.save()
    return total, grand


def make_discharge(path, s):
    h = HOSP[s["hospital"]]
    d = dict(s["discharge"])
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle("Discharge Summary")
    c.setCreator("HIMS Clinical Module v7.2")
    y = _hospital_header(c, h, "DISCHARGE SUMMARY")
    paras = {k: d.pop(k) for k in ["Past History", "Course in Hospital"] if k in d}
    y = _kv(c, y, d, gap=15)
    y -= 8
    for k, v in paras.items():
        y = _para(c, y, k, v)
    y -= 30
    _seal(c, y, s.get("seal_discharge", True), d.get("Treating Doctor", ""))
    _footer(c)
    c.save()


def make_prescription(path, s):
    h = HOSP[s["hospital"]]
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle("Prescription")
    c.setCreator("HIMS Clinical Module v7.2")
    y = _hospital_header(c, h, "DISCHARGE PRESCRIPTION")
    y = _kv(c, y, {"Patient Name": s["discharge"]["Patient Name"], "Date": s["discharge"]["Date of Discharge"],
                   "Prescribed by": s["discharge"]["Treating Doctor"]})
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y - 10, "Rx")
    y -= 32
    c.setFont("Helvetica", 10)
    for i, line in enumerate(s["prescription"], 1):
        c.drawString(55, y, f"{i}. {line}")
        y -= 16
    _footer(c)
    c.save()


def tamper(path: Path, producer: str, created: str, modified: str):
    """Simulate a bill edited in an image editor after issue (sets forensic metadata)."""
    reader = PdfReader(str(path))
    writer = PdfWriter()
    for p in reader.pages:
        writer.add_page(p)
    writer.add_metadata({"/Producer": producer, "/Creator": producer,
                         "/CreationDate": created, "/ModDate": modified, "/Title": "Final Bill"})
    with open(path, "wb") as fh:
        writer.write(fh)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    index = []
    for s in SCENARIOS:
        d = OUT / s["id"]
        d.mkdir()
        skip = set(s.get("skip", []))
        make_claim_form(d / "claim_form.pdf", s)
        items_total, grand = make_bill(d / "hospital_bill.pdf", s)
        if s.get("tamper"):
            tamper(d / "hospital_bill.pdf", s["tamper"], "D:20261028101500+05'30'", "D:20261102213000+05'30'")
        if "discharge_summary" not in skip and s.get("discharge"):
            make_discharge(d / "discharge_summary.pdf", s)
        if s.get("prescription"):
            make_prescription(d / "prescription.pdf", s)
        meta = {
            "claim_id": s["id"], "title": s["title"], "expected": s["expected"],
            "hospital_id": s["hospital"], "patient": s["claim_form"]["Patient Name"],
            "diagnosis": s["claim_form"]["Diagnosis"], "claimed_amount": s["claim_form"]["Total Amount Claimed"],
            "files": sorted(p.name for p in d.glob("*.pdf")),
        }
        (d / "scenario.json").write_text(json.dumps(meta, indent=2))
        index.append(meta)
        print(f"  {s['id']}: {len(meta['files'])} docs  items_total={items_total:,} grand={grand:,}  -> {s['title']}")
    (OUT / "index.json").write_text(json.dumps(index, indent=2))
    print(f"Generated {len(index)} claim packages in {OUT} at {datetime.now():%H:%M:%S}")


if __name__ == "__main__":
    main()
