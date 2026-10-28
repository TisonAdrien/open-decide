"""Structured field extraction from raw text.

The engine routes on free text. Some workflows also need a few typed fields
(amount, date, email, phone, IBAN, invoice number) that are better extracted
with deterministic regex than with a decision model.

This module is pure, dependency-free, and fully tested. It is meant to run
*before* the engine: ``extract_fields(text)`` returns a dict that the API can
attach to the run input (e.g. as a JSON header) or expose separately.

Design:

- Each field has an ordered list of regex patterns, tried in order.
- The first match wins and is normalised (e.g. amounts to a float in the
  original currency, dates to ISO 8601, emails to lowercase).
- Extraction is best-effort: missing fields are simply omitted from the result.
- No external dependency: regex only, which is the recommended approach for
  predictable shapes like amounts, dates and emails.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

_AMOUNT_RE = re.compile(
    r"""
    (?<![A-Za-z0-9])
    (?:
        (?P<currency_prefix>
            [$\u20AC\u00A3\u00A5\u20B9]
            |\bEUR\b|\bUSD\b|\bGBP\b|\bCHF\b|\bCAD\b|\bAUD\b|\bJPY\b|\bINR\b
        )
        \s*
    )?
    (?P<sign>-)?\s*
    (?P<number>
        \d{1,3}(?:[ \u00A0,.]\d{3})+(?:[.,]\d{1,2})?
        |
        \d+(?:[.,]\d{1,2})
    )
    (?:
        \s*
        (?P<currency_suffix>
            \bEUR\b|\bUSD\b|\bGBP\b|\bCHF\b|\bCAD\b|\bAUD\b|\bJPY\b|\bINR\b
            |[$\u20AC\u00A3\u00A5\u20B9]
        )
    )?
    """,
    re.VERBOSE,
)

_DATE_PATTERNS = [
    # ISO 2026-10-28
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), ("y", "m", "d")),
    # FR/EU 28/10/2026 or 28-10-2026
    (re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b"), ("d", "m", "y")),
    # US 10/28/2026 (detected only if first part > 12)
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), ("m", "d", "y")),
]

_MONTHS_FR = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
}
_MONTHS_EN = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_NAME_RE = re.compile(
    r"\b(\d{1,2})\s+(" + "|".join(list(_MONTHS_FR) + list(_MONTHS_EN)) + r")\s+(\d{4})\b",
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

_PHONE_RE = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s.\-]?)?(?:\(?\d{1,4}\)?[\s.\-]?){2,4}\d{1,4}(?!\d)")

_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}[ ]?[A-Z0-9]{1,4}\b")

_INVOICE_RE = re.compile(
    r"\b(?:invoice|facture|ref(?:erence)?|n[°o])\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/]{2,20})\b",
    re.IGNORECASE,
)

_CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}
_CURRENCY_CODES = {"EUR", "USD", "GBP", "CHF", "CAD", "AUD", "JPY", "INR", "RS", "R$"}


def extract_fields(text: str) -> dict[str, Any]:
    """Best-effort structured extraction from free text.

    Returns a dict with any of: ``amounts``, ``dates``, ``emails``, ``phones``,
    ``ibans``, ``invoice_numbers``. Missing fields are omitted. All lists are
    deduplicated while preserving order.
    """
    if not text or not text.strip():
        return {}

    result: dict[str, Any] = {}

    amounts = _extract_amounts(text)
    if amounts:
        result["amounts"] = amounts

    dates = _extract_dates(text)
    if dates:
        result["dates"] = dates

    emails = _unique([m.lower() for m in _EMAIL_RE.findall(text)])
    if emails:
        result["emails"] = emails

    phones = _unique([_normalise_phone(p) for p in _PHONE_RE.findall(text)])
    phones = [p for p in phones if p and 7 <= len(re.sub(r"\D", "", p)) <= 15]
    if phones:
        result["phones"] = phones

    ibans = _unique([re.sub(r"\s", "", m).upper() for m in _IBAN_RE.findall(text)])
    if ibans:
        result["ibans"] = ibans

    invoices = _unique([m.upper() for m in _INVOICE_RE.findall(text)])
    if invoices:
        result["invoice_numbers"] = invoices

    return result


# --------------------------------------------------------------------------- #
# Field extractors
# --------------------------------------------------------------------------- #


def _extract_amounts(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for match in _AMOUNT_RE.finditer(text):
        raw = match.group("number")
        if not raw:
            continue
        value = _parse_number(raw)
        if value is None:
            continue
        if match.group("sign") == "-":
            value = -value
        currency = match.group("currency_prefix") or match.group("currency_suffix") or None
        out.append(
            {
                "value": value,
                "currency": _normalise_currency(currency),
                "raw": match.group(0).strip(),
            }
        )
    return _dedupe_dicts(out, key=("value", "currency"))


def _extract_dates(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    for pattern, order in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            parts = match.groups()
            iso = _to_iso(parts, order)
            if iso and iso not in seen:
                seen.add(iso)
                out.append(iso)

    for match in _MONTH_NAME_RE.finditer(text):
        day = int(match.group(1))
        month_name = match.group(2).lower()
        year = int(match.group(3))
        month = _MONTHS_FR.get(month_name) or _MONTHS_EN.get(month_name)
        if month:
            try:
                iso = date(year, month, day).isoformat()
            except ValueError:
                continue
            if iso not in seen:
                seen.add(iso)
                out.append(iso)

    return out


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _parse_number(raw: str) -> float | None:
    cleaned = raw.replace("\u00a0", "").replace(" ", "")
    # If both , and . are present, the last one is the decimal separator
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # 1,234 -> 1234 if 3 digits after comma, else decimal
        tail = cleaned.split(",")[-1]
        cleaned = cleaned.replace(",", "." if len(tail) <= 2 else "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _normalise_currency(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw in _CURRENCY_SYMBOLS:
        return _CURRENCY_SYMBOLS[raw]
    upper = raw.upper().rstrip(".")
    if upper in _CURRENCY_CODES:
        return "INR" if upper == "RS" else upper
    return upper


def _normalise_phone(raw: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", raw)
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    return cleaned


def _to_iso(parts: tuple[str, ...], order: tuple[str, ...]) -> str | None:
    values = dict(zip(order, parts, strict=True))
    try:
        year = int(values.get("y", "0"))
        month = int(values.get("m", "0"))
        day = int(values.get("d", "0"))
    except ValueError:
        return None
    if year < 100:
        year += 2000 if year < 70 else 1900
    # US heuristic: if order is m,d,y and first part > 12, swap
    if order == ("m", "d", "y") and month > 12:
        month, day = day, month
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _dedupe_dicts(items: list[dict[str, Any]], key: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        k = tuple(item.get(f) for f in key)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out
