from app.mini_graph import END, START, MiniStateGraph
from app.state import ClaimState
from app.tools import knowledge_base as kb
from app.tools.document_reader import forensic_flags, read_document
from app.tools.extractor import classify, extract_fields
from app.tools.utils import inr, parse_date, parse_money, similarity


def test_money_and_dates():
    assert parse_money("Rs. 1,20,000.00") == 120000.0
    assert parse_money("₹38,450") == 38450.0
    assert inr(120000) == "₹1,20,000"
    assert inr(38450) == "₹38,450"
    assert str(parse_date("14-10-2026")) == "2026-10-14"
    assert similarity("Kiran Kumar P", "Kiran Kumar") > 0.75


def test_classify_and_extract_bill(sample_files):
    bill = next(f for f in sample_files("CLM-2026-1004") if f.name == "hospital_bill.pdf")
    doc = read_document(bill)
    dtype, conf = classify(doc["text"], doc["file"])
    assert dtype == "hospital_bill" and conf > 0.5
    fields = extract_fields(dtype, doc["text"])
    assert fields["gross_total"] == 120000.0
    assert len(fields["line_items"]) == 9
    assert sum(i["amount"] for i in fields["line_items"]) == 123300.0
    assert forensic_flags(doc["metadata"]), "tampered bill should raise forensic flags"


def test_clean_pdf_has_no_forensic_flags(sample_files):
    doc = read_document(sample_files("CLM-2026-1001")[0])
    assert forensic_flags(doc["metadata"]) == []


def test_knowledge_lookups():
    assert kb.find_policy("POL-HS-240011")["proposer"] == "Anil Kumar"
    h, how = kb.find_hospital("Shree Sai Clinic & Nursing Home")
    assert h["watchlist"] and how.startswith("name")
    key, entry, how = kb.find_diagnosis("Dengue Fever with Thrombocytopenia")
    assert key == "dengue fever"
    assert kb.find_diagnosis(None, "K35.80")[0] == "acute appendicitis"
    assert kb.has_term("CT Scan Abdomen", "ct") and not kb.has_term("Contact lens", "ct")


def test_mini_graph_fan_out_join():
    order = []

    def node(name):
        def fn(state):
            order.append(name)
            return {"trace": [name]}
        return fn

    g = MiniStateGraph(ClaimState)
    for n in "abcd":
        g.add_node(n, node(n))
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("a", "c")
    g.add_edge(["b", "c"], "d")
    g.add_edge("d", END)
    out = g.compile().invoke({})
    assert out["trace"] == ["a", "b", "c", "d"] and order[-1] == "d"
