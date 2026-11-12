"""Gloss: a deterministic check of an answer against the passages it cites.

A medieval gloss is the note a reader writes in the margin beside a line of
text. Here the "reader" is a small, dependency-free checker that runs after the
model has answered. It splits the answer into claims, resolves each
``[filename, Page N]`` citation to the passages that were actually retrieved,
and measures how much of the claim's wording those passages contain.

It does not use a model, so the result is reproducible and cheap, and it is
honest about what it is: a lexical overlap check. It catches citations that
point at nothing, numbers that are not in the cited passage and sentences that
carry no citation at all. It cannot judge paraphrase or reasoning.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

CITATION_RE = re.compile(r"\[([^\[\]\n]+?),\s*Page\s*(\d+)\]", re.IGNORECASE)
_TRAILING_CITES_RE = re.compile(r"([.!?])\s*((?:\[[^\[\]\n]+?,\s*Page\s*\d+\]\s*)+)", re.IGNORECASE)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")
_WORD_RE = re.compile(r"[a-z][a-z'-]+")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")

SUPPORTED_AT = 0.6
PARTIAL_AT = 0.3
MIN_CONTENT_WORDS = 3

STOPWORDS = frozenset(
    """a about above after again all also am an and any are as at be because been before being below
    between both but by can could did do does doing down during each few for from further had has have
    having he her here hers him his how i if in into is it its itself just me more most my no nor not of
    off on once only or other our ours out over own same she should so some such than that the their
    theirs them then there these they this those through to too under until up very was we were what
    when where which while who whom why will with would you your yours according based document
    documents states stated mentions mentioned provided context source sources page""".split()
)

DISCLAIMER_MARKERS = ("general knowledge", "do not contain", "does not contain", "no context available")


def _stem(word: str) -> str:
    """Tiny suffix stripper so 'payments' matches 'payment' and 'reported' matches 'reporting'."""
    for suffix in ("ations", "ation", "ingly", "ments", "ment", "ings", "ing", "edly", "ied", "ies", "ed", "es", "ly", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def content_terms(text: str) -> List[str]:
    return [_stem(w.strip("'-")) for w in _WORD_RE.findall(text.lower()) if w not in STOPWORDS and len(w) > 2]


def _numbers(text: str) -> List[str]:
    return [n.replace(",", "") for n in _NUMBER_RE.findall(text)]


def _strip_markdown(line: str) -> str:
    line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)   # list markers
    line = re.sub(r"[*_`]+", "", line)                     # emphasis and inline code ticks
    return line.strip()


def split_claims(answer: str) -> List[str]:
    """Break an answer into sentence-sized claims, skipping headings, tables and code."""
    text = _FENCE_RE.sub(" ", answer or "")
    # "Fact. [a.pdf, Page 2]" -> "Fact [a.pdf, Page 2]." so the citation stays with its sentence
    text = _TRAILING_CITES_RE.sub(lambda m: " " + m.group(2).strip() + m.group(1) + " ", text)
    claims: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("|") or set(line) <= set("-=*_ "):
            continue
        line = _strip_markdown(line)
        if line.endswith(":") and not CITATION_RE.search(line):
            continue  # a lead-in such as "Key points:"
        for sentence in _SENTENCE_SPLIT_RE.split(line):
            sentence = sentence.strip()
            if sentence:
                claims.append(sentence)
    return claims


def _same_file(cited: str, filename: str) -> bool:
    a, b = cited.strip().lower(), (filename or "").strip().lower()
    if not a or not b:
        return False
    return a == b or a == b.rsplit(".", 1)[0] or a.rsplit(".", 1)[0] == b


def _support(claim_terms: List[str], passages: List[str]) -> float:
    if not claim_terms:
        return 0.0
    vocabulary = set()
    for passage in passages:
        vocabulary.update(content_terms(passage))
    unique = set(claim_terms)
    return len(unique & vocabulary) / len(unique)


def _status(support: float) -> str:
    if support >= SUPPORTED_AT:
        return "supported"
    if support >= PARTIAL_AT:
        return "partial"
    return "unsupported"


def audit_answer(answer: str, sources: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Return a per-claim verdict and a summary for one assistant answer.

    Claim statuses:
      supported    cited, and the cited passage contains most of the claim's terms
      partial      cited, the cited passage contains some of them
      unsupported  cited, the cited passage contains few of them
      phantom      cites a file/page that was not among the retrieved passages
      traceable    not cited, but a retrieved passage contains most of its terms
      uncited      not cited and not found in any retrieved passage
    """
    sources = [s for s in (sources or []) if isinstance(s, dict)]
    claims_out: List[Dict[str, Any]] = []
    counts = {k: 0 for k in ("supported", "partial", "unsupported", "phantom", "traceable", "uncited")}

    for sentence in split_claims(answer):
        citations = CITATION_RE.findall(sentence)
        bare = CITATION_RE.sub(" ", sentence)
        terms = content_terms(bare)
        if any(marker in bare.lower() for marker in DISCLAIMER_MARKERS) and not citations:
            continue  # the model's own "not in your documents" notice is not a factual claim
        if len(set(terms)) < MIN_CONTENT_WORDS and not citations:
            continue

        entry: Dict[str, Any] = {"text": re.sub(r"\s+", " ", bare).strip(" .") , "citations": [], "notes": []}

        if citations:
            matched_passages: List[str] = []
            for cited_file, cited_page in citations:
                page = int(cited_page)
                hits = [s for s in sources if _same_file(cited_file, s.get("filename", "")) and int(s.get("page_number") or 0) == page]
                entry["citations"].append({"filename": cited_file.strip(), "page": page, "found": bool(hits)})
                matched_passages.extend(s.get("text_content", "") for s in hits)

            missing = [c for c in entry["citations"] if not c["found"]]
            if not matched_passages:
                entry["status"] = "phantom"
                entry["support"] = 0.0
                entry["notes"].append("Cites a passage that was not retrieved for this answer.")
            else:
                support = _support(terms, matched_passages)
                entry["support"] = round(support, 2)
                entry["status"] = _status(support)
                if missing:
                    entry["notes"].append(
                        "Also cites %s, which was not retrieved." % ", ".join("%s p.%d" % (c["filename"], c["page"]) for c in missing)
                    )
                joined = " ".join(matched_passages)
                source_numbers = set(_numbers(joined))
                absent = [n for n in _numbers(bare) if n not in source_numbers]
                if absent:
                    entry["notes"].append("Figure not found in the cited passage: %s." % ", ".join(sorted(set(absent))))
                    if entry["status"] == "supported":
                        entry["status"] = "partial"
        else:
            best_support, best_source = 0.0, None
            for source in sources:
                value = _support(terms, [source.get("text_content", "")])
                if value > best_support:
                    best_support, best_source = value, source
            entry["support"] = round(best_support, 2)
            if best_source is not None and best_support >= SUPPORTED_AT:
                entry["status"] = "traceable"
                entry["notes"].append(
                    "No citation given; wording matches %s p.%s." % (best_source.get("filename", "a source"), best_source.get("page_number", "?"))
                )
            else:
                entry["status"] = "uncited"

        counts[entry["status"]] += 1
        claims_out.append(entry)

    total = len(claims_out)
    grounded = counts["supported"] + counts["traceable"]
    return {
        "claims": claims_out,
        "summary": {
            "total": total,
            **counts,
            # share of claims whose wording is actually found in a retrieved passage
            "grounding": round(grounded / total, 2) if total else None,
            "retrieved_passages": len(sources),
        },
        "method": "lexical-overlap-v1",
    }
