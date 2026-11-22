import importlib.util
import os

# Load the module by path: it has no dependencies, so the test needs no database or model.
_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend/app/retrieval/gloss.py"))
_spec = importlib.util.spec_from_file_location("gloss", _path)
gloss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gloss)

SOURCES = [
    {
        "document_id": 1, "filename": "leave-policy.pdf", "chunk_index": 0, "page_number": 2, "similarity_score": 0.81,
        "text_content": "Full-time employees accrue 18 days of paid annual leave per calendar year. "
                        "Unused leave of up to 5 days may be carried forward into the next year.",
    },
    {
        "document_id": 1, "filename": "leave-policy.pdf", "chunk_index": 3, "page_number": 4, "similarity_score": 0.64,
        "text_content": "Requests for parental leave must be submitted to the HR department at least 30 days in advance.",
    },
]


def _by_status(report):
    return {c["status"]: c for c in report["claims"]}


def test_split_keeps_trailing_citation_with_its_sentence():
    claims = gloss.split_claims("Employees accrue 18 days of leave. [leave-policy.pdf, Page 2] Requests go to HR.")
    assert len(claims) == 2
    assert "[leave-policy.pdf, Page 2]" in claims[0]
    assert "Page 2" not in claims[1]


def test_split_skips_headings_tables_and_code():
    answer = "## Summary\n\n| a | b |\n|---|---|\n\n```python\nprint('paid annual leave days')\n```\n\n- Employees accrue paid annual leave every year.\n"
    assert gloss.split_claims(answer) == ["Employees accrue paid annual leave every year."]


def test_supported_claim():
    report = gloss.audit_answer("Full-time employees accrue 18 days of paid annual leave each year [leave-policy.pdf, Page 2].", SOURCES)
    claim = report["claims"][0]
    assert claim["status"] == "supported"
    assert claim["citations"] == [{"filename": "leave-policy.pdf", "page": 2, "found": True}]
    assert report["summary"]["grounding"] == 1.0


def test_wrong_number_is_downgraded_and_named():
    report = gloss.audit_answer("Full-time employees accrue 25 days of paid annual leave each year [leave-policy.pdf, Page 2].", SOURCES)
    claim = report["claims"][0]
    assert claim["status"] == "partial"
    assert any("25" in note for note in claim["notes"])


def test_phantom_citation():
    report = gloss.audit_answer("Sabbaticals last six months for senior staff [handbook.pdf, Page 9].", SOURCES)
    assert report["claims"][0]["status"] == "phantom"
    assert report["summary"]["phantom"] == 1
    # right file, wrong page is still a passage that was never retrieved
    report = gloss.audit_answer("Employees accrue paid annual leave [leave-policy.pdf, Page 7].", SOURCES)
    assert report["claims"][0]["status"] == "phantom"


def test_cited_but_unrelated_is_unsupported():
    report = gloss.audit_answer("The cafeteria serves vegetarian lunches on weekdays [leave-policy.pdf, Page 4].", SOURCES)
    assert report["claims"][0]["status"] == "unsupported"


def test_uncited_claim_is_traced_or_flagged():
    report = gloss.audit_answer(
        "Parental leave requests must be submitted to the HR department 30 days in advance. "
        "Most companies in Europe offer much longer holidays.",
        SOURCES,
    )
    found = _by_status(report)
    assert "leave-policy.pdf p.4" in found["traceable"]["notes"][0]
    assert "uncited" in found
    assert report["summary"]["total"] == 2
    assert report["summary"]["grounding"] == 0.5


def test_citation_without_extension_and_case_still_resolves():
    report = gloss.audit_answer("Unused leave of up to 5 days may be carried forward [Leave-Policy, page 2].", SOURCES)
    assert report["claims"][0]["status"] == "supported"


def test_disclaimer_and_empty_answers():
    report = gloss.audit_answer(
        "I am answering using general knowledge because the uploaded documents do not contain the details.", []
    )
    assert report["claims"] == []
    assert report["summary"]["grounding"] is None
    assert gloss.audit_answer("", None)["summary"]["total"] == 0
