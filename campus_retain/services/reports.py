"""Excel and PDF exports of real college data. Private details (secret identifying
detail, claimant phone numbers, proof text) are never exported."""
import io

from fpdf import FPDF
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from ..serializers import day, iso

HEADER_FILL = PatternFill("solid", fgColor="EDE9FE")


def safe_cell(value):
    """Spreadsheet-formula neutralising for user-entered text (CSV/Excel injection)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _sheet(ws, header, rows, widths=None):
    ws.append(header)
    for cell in ws[1]:
        cell.font, cell.fill = Font(bold=True), HEADER_FILL
    for row in rows:
        ws.append([safe_cell(v) for v in row])
    ws.freeze_panes = "A2"
    for i, h in enumerate(header, start=1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(h, max(12, min(40, len(h) + 4)))


def item_rows(items):
    for item in items:
        claim = item.claims[-1] if item.claims else None
        yield [item.id, item.kind, item.name, item.category, item.location,
               item.campus.name if item.campus else "", item.status, iso(item.date_found),
               day(item.occurred_on), item.reported_by.email if item.reported_by else "",
               item.collection_point.name if item.collection_point else "",
               claim.status if claim else "", claim.student_email if claim else "",
               claim.reviewed_by.email if claim and claim.reviewed_by else "",
               iso(claim.reviewed_at) if claim else "", iso(claim.collected_at) if claim else "",
               claim.collected_by.email if claim and claim.collected_by else ""]


ITEM_HEADER = ["Item ID", "Type", "Name", "Category", "Location", "Campus", "Status",
               "Reported at (UTC)", "Date found/lost", "Reported by", "Collection point",
               "Latest claim status", "Claimant email", "Reviewed by", "Reviewed at (UTC)",
               "Collected at (UTC)", "Handed over by"]


def analytics_workbook(college, data, items):
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    t = data["totals"]
    rate = f"{t['recovery_rate'] * 100:.1f}%" if t["recovery_rate"] is not None else "n/a"
    _sheet(ws, ["Measure", "Value"], [
        ["College", college.name],
        ["Period", f"{data['period']['from']} to {data['period']['to']}"],
        ["Found items reported", t["found_reported"]],
        ["Lost items reported", t["lost_reported"]],
        ["Found items recovered (approved or collected)", t["recovered"]],
        ["Recovery rate", rate],
        ["Pickups confirmed", t["returned"]],
        ["Average days from report to pickup", t["avg_days_to_return"] if t["avg_days_to_return"] is not None else "n/a"],
        ["Median days from report to pickup", t["median_days_to_return"] if t["median_days_to_return"] is not None else "n/a"],
        ["Claims submitted", t["claims_submitted"]],
        ["Claims waiting for review (now)", data["backlog"]["pending_claims"]],
        ["Approved, awaiting pickup (now)", data["backlog"]["awaiting_pickup"]],
        ["Found items unclaimed for 30+ days (now)", data["backlog"]["unclaimed_over_30_days"]],
    ], widths={"Measure": 48, "Value": 28})
    _sheet(wb.create_sheet("Monthly"), ["Month", "Found reported", "Lost reported", "Pickups confirmed"],
           [[m["month"], m["found"], m["lost"], m["returned"]] for m in data["monthly"]])
    _sheet(wb.create_sheet("By category"), ["Category", "Found reported", "Recovered"],
           [[c["category"], c["found"], c["recovered"]] for c in data["by_category"]])
    _sheet(wb.create_sheet("By campus"), ["Campus", "Found reported", "Recovered"],
           [[c["campus"], c["found"], c["recovered"]] for c in data["by_campus"]])
    _sheet(wb.create_sheet("Claim outcomes"), ["Outcome", "Claims"],
           [[k, v] for k, v in data["claim_outcomes"].items()])
    _sheet(wb.create_sheet("Items"), ITEM_HEADER, item_rows(items), widths={"Name": 28, "Location": 28})
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class _PDF(FPDF):
    title_text = ""

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(110, 110, 120)
        self.cell(0, 8, self.title_text, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(130, 130, 140)
        self.cell(0, 8, f"Campus Retain - page {self.page_no()}", align="C")


def _latin(text):
    # Core PDF fonts are Latin-1 only; replace anything else rather than failing.
    return str(text).encode("latin-1", "replace").decode("latin-1")


def analytics_pdf(college, data, generated_by):
    pdf = _PDF(format="A4")
    pdf.title_text = _latin(f"{college.name} - lost & found report")
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, _latin(college.name), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _latin(f"Lost & found report, {data['period']['from']} to {data['period']['to']}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _latin(f"Generated by {generated_by}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    t, b = data["totals"], data["backlog"]
    rate = f"{t['recovery_rate'] * 100:.1f}%" if t["recovery_rate"] is not None else "n/a"
    rows = [
        ("Found items reported", t["found_reported"]), ("Lost items reported", t["lost_reported"]),
        ("Recovered (approved or collected)", t["recovered"]), ("Recovery rate", rate),
        ("Pickups confirmed", t["returned"]),
        ("Average days to pickup", t["avg_days_to_return"] if t["avg_days_to_return"] is not None else "n/a"),
        ("Median days to pickup", t["median_days_to_return"] if t["median_days_to_return"] is not None else "n/a"),
        ("Claims submitted", t["claims_submitted"]),
        ("Waiting for review now", b["pending_claims"]), ("Awaiting pickup now", b["awaiting_pickup"]),
        ("Unclaimed 30+ days now", b["unclaimed_over_30_days"]),
    ]
    _table(pdf, ["Measure", "Value"], [[k, v] for k, v in rows], [120, 60])
    pdf.ln(4)
    _heading(pdf, "By month")
    _table(pdf, ["Month", "Found", "Lost", "Pickups"],
           [[m["month"], m["found"], m["lost"], m["returned"]] for m in data["monthly"]], [60, 40, 40, 40])
    pdf.ln(4)
    _heading(pdf, "By category")
    _table(pdf, ["Category", "Found", "Recovered"],
           [[c["category"], c["found"], c["recovered"]] for c in data["by_category"]] or [["No items", "", ""]],
           [100, 40, 40])
    if len(data["by_campus"]) > 1:
        pdf.ln(4)
        _heading(pdf, "By campus")
        _table(pdf, ["Campus", "Found", "Recovered"],
               [[c["campus"], c["found"], c["recovered"]] for c in data["by_campus"]], [100, 40, 40])
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(0, 4, "Recovery rate = found items reported in the period that now have an approved or "
                         "collected claim, divided by found items reported. Days to pickup are measured from the "
                         "report to the pickup confirmed at the desk. Removed listings are excluded.")
    return bytes(pdf.output())


def _heading(pdf, text):
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _latin(text), new_x="LMARGIN", new_y="NEXT")


def _table(pdf, header, rows, widths):
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(237, 233, 254)
    for h, w in zip(header, widths):
        pdf.cell(w, 7, _latin(h), border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for row in rows:
        for v, w in zip(row, widths):
            pdf.cell(w, 6, _latin(v)[:60], border=1)
        pdf.ln()
