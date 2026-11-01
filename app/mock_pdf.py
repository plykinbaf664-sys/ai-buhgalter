"""Mock-only print form. Real adapters must use the native 1C print form."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.domain import InvoicePreview, PdfDocument
from app.presentation import money, quantity

ASSETS = Path(__file__).with_name("assets")
pdfmetrics.registerFont(TTFont("InvoiceSans", str(ASSETS / "NotoSans-Regular.ttf")))
pdfmetrics.registerFont(TTFont("InvoiceSansBold", str(ASSETS / "NotoSans-Bold.ttf")))
pdfmetrics.registerFontFamily("InvoiceSans", normal="InvoiceSans", bold="InvoiceSansBold")
INK = colors.HexColor("#172b40")
GRAY = colors.HexColor("#edf2f6")


def render_mock_pdf(preview: InvoicePreview) -> PdfDocument:
    preview = InvoicePreview.model_validate(preview)
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, leftMargin=28, rightMargin=28,
                            topMargin=30, bottomMargin=40, title="TEST / MOCK Tax Invoice",
                            author="Fictitious test company", invariant=1)
    body = ParagraphStyle("body", fontName="InvoiceSans", fontSize=8.5, leading=12, textColor=INK,
                          splitLongWords=True)
    small = ParagraphStyle("small", parent=body, fontSize=7.2, leading=10)
    heading = ParagraphStyle("heading", parent=body, fontName="InvoiceSansBold", fontSize=11, leading=16)
    title = ParagraphStyle("title", parent=heading, fontSize=25, leading=30)
    numeric = ParagraphStyle("numeric", parent=small, alignment=2, wordWrap="CJK")

    def p(value, style=body):
        return Paragraph(escape(str(value)), style)

    def block(label, values):
        return [p(label, heading), Spacer(1, 5)] + [p(value) for value in values]

    def pair(left, right):
        table = Table([[left, right]], colWidths=[doc.width / 2, doc.width / 2])
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#cbd5df")),
            ("LINEBEFORE", (1, 0), (1, 0), .5, colors.HexColor("#cbd5df"))]))
        return table

    story = [pair(block("LOGO / TEST COMPANY", ["Fictitious accounting services"]),
                  [p("TAX INVOICE", title), p("TEST / MOCK - DO NOT PAY", heading),
                   p(f"Invoice No.: {preview.reference}"), p(f"Date of Issuing: {preview.invoice_date:%d.%m.%Y}"),
                   p(f"Date of Supply: {preview.supply_date:%d.%m.%Y}")]), Spacer(1, 14)]
    parties = []
    for label, party in (("Issued By", preview.issuer), ("Issued To", preview.recipient)):
        parties.append(block(label, [party.name, party.address, f"TRN: {party.tax_number}",
                                    f"Tel: {party.phone}", f"Email: {party.email}"]))
    story.extend([pair(*parties), Spacer(1, 10), pair(
        block("Bank Details", [f"Bank: {preview.bank.bank}", f"IBAN: {preview.bank.iban}",
                               f"SWIFT: {preview.bank.swift}", f"Beneficiary: {preview.bank.beneficiary}"]),
        block("Payment and Delivery Terms", [f"Payment Terms: {preview.terms.payment}",
                                             f"Delivery Terms: {preview.terms.delivery}"])), Spacer(1, 18)])
    headers = ("No.", "Description", "Quantity", "UOM", "Price Excl. VAT", "Amount Excl. VAT", "VAT %",
               "VAT Amount", "Amount Incl. VAT")
    rows = [[p(h, small) for h in headers]]
    for i, line in enumerate(preview.lines, 1):
        description = line.description
        if line.tax.rate == 0:
            description += f" ({line.tax.label})"
        rows.append([p(i, small), p(description, body), p(quantity(line.quantity), numeric), p(line.uom, small),
                     p(money(line.price), numeric), p(money(line.subtotal), numeric), p(quantity(line.tax.rate), numeric),
                     p(money(line.tax_amount), numeric), p(money(line.total), numeric)])
    widths = [22, 180, 42, 40, 56, 60, 32, 51, 56]
    table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), GRAY), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#cbd5df")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story += [p(f"Services and amounts ({preview.currency})", heading), Spacer(1, 6), table, Spacer(1, 14)]
    totals = Table([[p(label, heading if label == "Total" else body), p(f"{money(value)} {preview.currency}", heading)]
                    for label, value in (("Sub Total", preview.subtotal), ("Total VAT", preview.tax_amount),
                                         ("Total", preview.total))], colWidths=[90, 160], hAlign="RIGHT")
    totals.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 1, INK),
                               ("BACKGROUND", (0, -1), (-1, -1), GRAY), ("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    story.append(KeepTogether([p("Amount in words: " + preview.amount_in_words), Spacer(1, 10), totals,
        Spacer(1, 25), pair(block("Released By", ["Name / signature: __________________"]),
                            block("Received By", ["Name / signature: __________________"]))]))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("InvoiceSans", 7)
        canvas.setFillColor(colors.HexColor("#65778a"))
        canvas.drawString(28, 22, "TEST / MOCK - Fictitious data. Not valid for payment or tax reporting.")
        canvas.drawRightString(A4[0] - 28, 22, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return PdfDocument(content=stream.getvalue())
