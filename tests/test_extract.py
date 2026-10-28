"""Tests for structured field extraction."""

from __future__ import annotations

from open_decide.extract import extract_fields


def test_amount_eur() -> None:
    fields = extract_fields("Invoice total: 1 234,56 EUR")
    assert fields["amounts"][0]["value"] == 1234.56
    assert fields["amounts"][0]["currency"] == "EUR"


def test_amount_usd() -> None:
    fields = extract_fields("Total due: $1,234.56")
    assert fields["amounts"][0]["value"] == 1234.56
    assert fields["amounts"][0]["currency"] == "USD"


def test_multiple_amounts() -> None:
    fields = extract_fields("Subtotal: 100,00 EUR\nTax: 20,00 EUR\nTotal: 120,00 EUR")
    values = [a["value"] for a in fields["amounts"]]
    assert 100.0 in values and 20.0 in values and 120.0 in values


def test_date_iso() -> None:
    assert "2026-10-28" in extract_fields("Due on 2026-10-28.")["dates"]


def test_date_fr_slash() -> None:
    assert "2026-10-28" in extract_fields("Échéance le 28/10/2026.")["dates"]


def test_date_us_heuristic() -> None:
    assert "2026-10-28" in extract_fields("Due 10/28/2026.")["dates"]


def test_date_month_name_fr() -> None:
    assert "2026-10-28" in extract_fields("Le 28 octobre 2026.")["dates"]


def test_date_month_name_en() -> None:
    assert "2026-10-28" in extract_fields("On 28 October 2026.")["dates"]


def test_email() -> None:
    assert "alice@example.com" in extract_fields("Contact: Alice@Example.com")["emails"]


def test_phone_fr() -> None:
    fields = extract_fields("Appelez le +33 6 12 34 56 78.")
    assert any(p.startswith("+33612345678") for p in fields["phones"])


def test_iban() -> None:
    fields = extract_fields("IBAN: FR76 3000 6000 0112 3456 7890 189")
    assert fields["ibans"][0].startswith("FR76")


def test_invoice_number() -> None:
    fields = extract_fields("Please pay invoice INV-2026-0042 by Friday.")
    assert "INV-2026-0042" in fields["invoice_numbers"]


def test_empty_text() -> None:
    assert extract_fields("") == {}
    assert extract_fields("   ") == {}


def test_no_fields() -> None:
    assert extract_fields("hello world") == {}


def test_mixed() -> None:
    text = (
        "Facture INV-42 du 28/10/2026. Montant: 1 200,00 EUR. "
        "Contact: bob@example.com. Tel: +33 1 23 45 67 89."
    )
    fields = extract_fields(text)
    assert fields["amounts"][0]["value"] == 1200.0
    assert "2026-10-28" in fields["dates"]
    assert "bob@example.com" in fields["emails"]
    assert "INV-42" in fields["invoice_numbers"]


def test_invoice_ref_not_amount() -> None:
    """INV-42 should not be treated as amount 42.0."""
    fields = extract_fields("Invoice INV-42, total 1 234,56 EUR")
    values = [a["value"] for a in fields.get("amounts", [])]
    assert 42.0 not in values
    assert 1234.56 in values


def test_date_not_amount() -> None:
    """28/10/2026 should not produce amounts 28, 10 or 2026."""
    fields = extract_fields("Due 28/10/2026.")
    assert "amounts" not in fields
