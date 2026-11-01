"""Fictitious catalog and accounting settings. Never used by a real adapter."""
from datetime import date
from decimal import Decimal

from app.domain import (BankDetails, PartyDetails, PaymentTerms, ResolvedServiceSelection,
                        StrictModel, TaxProfile)


class FakeService(StrictModel):
    service_id: str
    description: str
    search_names: tuple[str, ...]
    price: Decimal
    uom: str = "Service"
    quantity: Decimal = Decimal("1")


class PreviousHint(StrictModel):
    reference: str
    client_id: str
    invoice_date: date
    services: tuple[ResolvedServiceSelection, ...]
    tax_id: str | None


SERVICES = (
    FakeService(service_id="service-accounting", description="Accounting and Bookkeeping services",
                search_names=("бухгалтерское обслуживание", "бухгалтерские услуги", "бухгалтерию",
                              "accounting and bookkeeping services"), price=Decimal("1000.00")),
    FakeService(service_id="service-legal", description="Legal consultation / Юридическая консультация",
                search_names=("юридическая консультация", "юридическую консультацию", "юридической консультации",
                              "legal consultation", "юридическую", "консультация", "консультацию"), price=Decimal("500.00")),
    FakeService(service_id="service-tax", description="Tax consultation / Налоговая консультация",
                search_names=("налоговая консультация", "налоговую консультацию", "tax consultation",
                              "налоговую", "консультация", "консультацию"), price=Decimal("300.00")),
)
TAXES = (
    TaxProfile(tax_id="test-vat-5", label="VAT 5% (test)", treatment="standard", rate=Decimal("5")),
    TaxProfile(tax_id="test-no-vat", label="Без НДС / Outside scope (test)", treatment="outside_scope", rate=Decimal("0")),
    TaxProfile(tax_id="test-zero", label="Zero rated (test)", treatment="zero_rated", rate=Decimal("0")),
    TaxProfile(tax_id="test-exempt", label="Exempt (test)", treatment="exempt", rate=Decimal("0")),
)
ISSUER = PartyDetails(name="Example Accounting FZ-LLC (TEST)", address="Suite 101, Example Test Building, Dubai, UAE",
                      tax_number="TEST-TRN-000001", phone="+971 00 000 0000", email="billing@example.invalid")
BANK = BankDetails(bank="Example Test Bank", iban="TEST-IBAN-NOT-FOR-PAYMENT", swift="TEST-ONLY",
                   beneficiary=ISSUER.name)
TERMS = PaymentTerms(payment="14 days from date of issue. TEST: do not pay.", delivery="Electronic delivery (test)")
PREVIOUS = PreviousHint(reference="TEST-PREV-2026-09", client_id="client-001", invoice_date=date(2026, 9, 1),
                        services=(ResolvedServiceSelection(service_id="service-accounting", quantity=Decimal("1")),),
                        tax_id="test-no-vat")


def recipient(name: str) -> PartyDetails:
    return PartyDetails(name=name, address="Office 202, Fictitious Test Street, Dubai, UAE",
                        tax_number="TEST-TRN-CLIENT", phone="+971 00 000 0001", email="client@example.invalid")


def amount_words(amount: Decimal, currency: str) -> str:
    small = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
             "fifteen sixteen seventeen eighteen nineteen").split()
    tens = "zero ten twenty thirty forty fifty sixty seventy eighty ninety".split()

    def below_thousand(n: int) -> str:
        words = []
        if n >= 100:
            words.extend((small[n // 100], "hundred")); n %= 100
        if n >= 20:
            words.append(tens[n // 10]); n %= 10
        if n or not words:
            words.append(small[n])
        return " ".join(words)

    whole = int(amount)
    words = []
    for size, label in ((10**9, "billion"), (10**6, "million"), (1000, "thousand")):
        if whole >= size:
            words.extend((below_thousand(whole // size), label)); whole %= size
    if whole or not words:
        words.append(below_thousand(whole))
    fraction = int((amount - int(amount)) * 100)
    return f'{" ".join(words).capitalize()} {currency} and {fraction:02d}/100 only'
