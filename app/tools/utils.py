"""Small, dependency-free helpers: dates, money, fuzzy matching."""
from __future__ import annotations

import re
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Optional

_DATE_FORMATS = (
    "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%d %B %Y",
    "%d.%m.%Y", "%b %d, %Y", "%d-%m-%y", "%d/%m/%y",
)


def parse_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value if not isinstance(value, datetime) else value.date()
    s = str(value).strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM|am|pm)?)", "", s).strip(" ,")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def fmt_date(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def parse_money(value) -> Optional[float]:
    """Parse '₹1,20,000.00', 'Rs. 38,450', 'INR 5,000' -> float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value)
    s = re.sub(r"(?i)(rs\.?|inr|₹)", "", s)
    m = re.search(r"-?[\d,]+(\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def inr(amount: Optional[float]) -> str:
    """Format a number using the Indian digit grouping: 120000 -> ₹1,20,000."""
    if amount is None:
        return "-"
    neg = amount < 0
    n = int(round(abs(amount)))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if neg else "") + "₹" + s


def norm(text: Optional[str]) -> str:
    if not text:
        return ""
    t = text.lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def similarity(a: Optional[str], b: Optional[str]) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # token containment helps with initials: "Kiran Kumar P" vs "Kiran Kumar"
    ta, tb = set(a.split()), set(b.split())
    contain = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return max(SequenceMatcher(None, a, b).ratio(), contain * 0.95)


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def age_on(dob: Optional[date], on: Optional[date]) -> Optional[int]:
    if not dob or not on:
        return None
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
