"""
Generates Investigator_Briefing_Guide.pdf: a short, non-technical guide for
commissioners and investigators seeing the Consolidated Intelligence
Platform for the first time -- how to log in, a guided walkthrough of each
screen, real-world case validation, and anticipated Q&A.

Run from backend/ with the venv active: python scripts/generate_guide.py
"""
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    HRFlowable, ListFlowable, ListItem, Flowable
)
from reportlab.pdfgen import canvas as pdfcanvas

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(HERE)
OUT_PATH = os.path.join(BACKEND_DIR, "..", "Investigator_Briefing_Guide.pdf")

# Palette matches the live application's own violet theme
VIOLET = colors.HexColor("#6a5cc4")
VIOLET_DARK = colors.HexColor("#4a3f96")
INK = colors.HexColor("#17152a")
DIM = colors.HexColor("#5b5470")
LINE = colors.HexColor("#e2ddf5")
PANEL = colors.HexColor("#f4f2fb")
GREEN = colors.HexColor("#2f8f5b")
AMBER = colors.HexColor("#b8790f")
RED = colors.HexColor("#c1453a")
WHITE = colors.white
PAGE_W, PAGE_H = A4

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverTitle", fontName="Helvetica-Bold", fontSize=27, leading=33,
                           textColor=INK, alignment=TA_CENTER, spaceAfter=6))
styles.add(ParagraphStyle(name="CoverSubtitle", fontName="Helvetica", fontSize=13, leading=18,
                           textColor=VIOLET_DARK, alignment=TA_CENTER, spaceAfter=4))
styles.add(ParagraphStyle(name="CoverMeta", fontName="Helvetica", fontSize=10.5, leading=15,
                           textColor=DIM, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="H1", fontName="Helvetica-Bold", fontSize=18, leading=23,
                           textColor=INK, spaceBefore=4, spaceAfter=10))
styles.add(ParagraphStyle(name="H2", fontName="Helvetica-Bold", fontSize=13, leading=17,
                           textColor=VIOLET_DARK, spaceBefore=14, spaceAfter=6))
styles.add(ParagraphStyle(name="Body", fontName="Helvetica", fontSize=10.3, leading=15,
                           textColor=INK, alignment=TA_LEFT, spaceAfter=6))
styles.add(ParagraphStyle(name="Mono", fontName="Courier", fontSize=9, leading=13,
                           textColor=INK, backColor=PANEL))
styles.add(ParagraphStyle(name="Caption", fontName="Helvetica-Oblique", fontSize=8.5, leading=12,
                           textColor=DIM, spaceBefore=2, spaceAfter=10))
styles.add(ParagraphStyle(name="TableHead", fontName="Helvetica-Bold", fontSize=9.2, leading=12, textColor=WHITE))
styles.add(ParagraphStyle(name="TableCell", fontName="Helvetica", fontSize=9.3, leading=13, textColor=INK))
styles.add(ParagraphStyle(name="StepNum", fontName="Helvetica-Bold", fontSize=16, leading=16, textColor=WHITE, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="StepTitle", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=INK))
styles.add(ParagraphStyle(name="StepBody", fontName="Helvetica", fontSize=9.6, leading=13.5, textColor=DIM))
styles.add(ParagraphStyle(name="Eyebrow", fontName="Courier-Bold", fontSize=9, leading=12,
                           textColor=VIOLET_DARK, spaceBefore=2, spaceAfter=4))
styles.add(ParagraphStyle(name="QuoteText", fontName="Helvetica-Oblique", fontSize=9.5, leading=14, textColor=INK))


def eyebrow(text):
    return Paragraph("} " + text.upper(), styles["Eyebrow"])


def h1(text):
    return Paragraph(text, styles["H1"])


def h2(text):
    return Paragraph(text, styles["H2"])


def body(text):
    return Paragraph(text, styles["Body"])


def bullets(items):
    return ListFlowable(
        [ListItem(Paragraph(it, styles["Body"]), leftIndent=10, bulletColor=VIOLET) for it in items],
        bulletType="bullet", start="circle", leftIndent=14, spaceBefore=2, spaceAfter=8,
    )


def rule():
    return HRFlowable(width="100%", thickness=0.6, color=LINE, spaceBefore=2, spaceAfter=10)


def data_table(header, rows, col_widths=None):
    header_row = [Paragraph(h, styles["TableHead"]) for h in header]
    body_rows = []
    for r in rows:
        cells = []
        for cell in r:
            cells.append(cell if isinstance(cell, Flowable) else Paragraph(str(cell), styles["TableCell"]))
        body_rows.append(cells)
    t = Table([header_row] + body_rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VIOLET_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PANEL]),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


class StepRow(Flowable):
    """A numbered walkthrough step: a filled circle with the step number,
    beside a title + body paragraph."""
    def __init__(self, number, title, body_text, width):
        super().__init__()
        self.number = number
        self.title = title
        self.body_text = body_text
        self.width = width
        self._title_p = Paragraph(title, styles["StepTitle"])
        self._body_p = Paragraph(body_text, styles["StepBody"])
        tw = width - 34
        _, th = self._title_p.wrap(tw, 1000)
        _, bh = self._body_p.wrap(tw, 1000)
        self.height = max(28, th + bh + 10)

    def draw(self):
        c = self.canv
        c.setFillColor(VIOLET)
        c.circle(11, self.height - 13, 11, stroke=0, fill=1)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(11, self.height - 17, str(self.number))
        tw = self.width - 34
        self._title_p.drawOn(c, 30, self.height - 15)
        self._body_p.drawOn(c, 30, self.height - 15 - self._title_p.wrap(tw, 1000)[1] - 3)


class FooterCanvas(pdfcanvas.Canvas):
    def showPage(self):
        self.setStrokeColor(LINE)
        self.setLineWidth(0.5)
        self.line(20 * mm, 15 * mm, PAGE_W - 20 * mm, 15 * mm)
        self.setFont("Helvetica", 7.5)
        self.setFillColor(DIM)
        self.drawString(20 * mm, 11 * mm, "Consolidated Intelligence Platform - Investigator Briefing Guide")
        self.drawRightString(PAGE_W - 20 * mm, 11 * mm, f"Page {self.getPageNumber()}")
        super().showPage()


def build():
    doc = SimpleDocTemplate(
        OUT_PATH, pagesize=A4,
        topMargin=18 * mm, bottomMargin=20 * mm, leftMargin=20 * mm, rightMargin=20 * mm,
        title="Consolidated Intelligence Platform - Investigator Briefing Guide",
        author="Team CARIBBEAN",
    )
    story = []

    # ---------------- Cover ----------------
    story.append(Spacer(1, 55 * mm))
    story.append(Paragraph("CONSOLIDATED INTELLIGENCE PLATFORM", styles["CoverTitle"]))
    story.append(Paragraph("Investigator Briefing &amp; Quick-Start Guide", styles["CoverSubtitle"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("A five-minute orientation for anyone seeing this system for the first time",
                            styles["CoverMeta"]))
    story.append(Spacer(1, 40))
    story.append(HRFlowable(width="50%", thickness=1, color=VIOLET, hAlign="CENTER"))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Team CARIBBEAN &middot; SIH26189", styles["CoverMeta"]))
    story.append(Paragraph(datetime.now().strftime("%d %B %Y"), styles["CoverMeta"]))
    story.append(PageBreak())

    # ---------------- What is this ----------------
    story.append(eyebrow("What This Is"))
    story.append(h1("In Plain Terms"))
    story.append(body(
        "Investigators already hold FIRs, call records, bank transaction records, surveillance reports "
        "and intelligence-agency reports on a case -- but they sit in separate systems, in free text and "
        "spreadsheets, and connecting them by hand is slow and error-prone. This system reads all of it, "
        "automatically works out who is really who (so \"Rajesh Kumar\" the accused and a different "
        "\"Rajesh Kumar\" who is just a witness never get mixed up), builds one relationship map, and "
        "flags the specific patterns organised networks use to look fragmented on paper -- mule-account "
        "chains, burner-SIM swaps, and recruiter-transporter-receiver trafficking chains."
    ))
    story.append(body(
        "<b>It never decides guilt.</b> Every single finding it produces is a <i>lead</i> that links back "
        "to the exact source records behind it, and is explicitly marked as requiring a human "
        "investigator's verification before anyone acts on it. The system's job ends where an "
        "investigator's judgement begins."
    ))
    story.append(h2("The one rule the whole system is built around"))
    story.append(Table(
        [[Paragraph("<b>DATA</b>", styles["TableCell"]), "->", Paragraph("<b>RELATIONSHIP</b>", styles["TableCell"]),
          "->", Paragraph("<b>PATTERN</b>", styles["TableCell"]), "->", Paragraph("<b>LEAD</b>", styles["TableCell"]),
          "->", Paragraph("<b>EVIDENCE</b>", styles["TableCell"]), "->", Paragraph("<b>HUMAN DECISION</b>", styles["TableCell"])]],
        colWidths=[20 * mm, 7 * mm, 30 * mm, 7 * mm, 22 * mm, 7 * mm, 18 * mm, 7 * mm, 22 * mm, 7 * mm, 30 * mm],
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph("It never becomes DATA -> AI -> PERSON SCORE -> GUILTY.", styles["Caption"]))
    story.append(PageBreak())

    # ---------------- How to access ----------------
    story.append(eyebrow("Getting In"))
    story.append(h1("How to Access the System"))
    story.append(body("Open a browser and go to the address given by the presenting team, then sign in with one of:"))
    story.append(data_table(
        ["Account", "Password", "What you'll see"],
        [
            ["investigator1", "investigator1pass", "Fraud Ring Alpha (financial network) case only"],
            ["investigator2", "investigator2pass", "Missing Persons - Sonepur Corridor (trafficking) case only"],
            ["admin1", "admin1pass", "Both cases, plus the audit-chain tamper/restore demo tools"],
        ],
        col_widths=[38 * mm, 52 * mm, 80 * mm],
    ))
    story.append(Spacer(1, 8))
    story.append(body(
        "For the fullest demo, sign in as <b>admin1</b> -- it has access to everything below. After "
        "signing in, pick a case and type a short reason for opening it (e.g. \"demo walkthrough\"). "
        "This is not a formality: every case you open is permanently logged to the tamper-evident audit "
        "chain, which is itself one of the things worth showing (Step 8)."
    ))
    story.append(PageBreak())

    # ---------------- Walkthrough ----------------
    story.append(eyebrow("Guided Walkthrough"))
    story.append(h1("What to Click, In Order"))
    story.append(body("Each screen is a tab on the left. Go through them top to bottom:"))
    story.append(Spacer(1, 6))

    steps = [
        ("Overview", "The case at a glance: how many people/phones/accounts are involved, how many "
         "leads have been found, and the highest-severity findings. This is the \"one-screen summary\" "
         "for a commissioner who has thirty seconds."),
        ("Graph", "The actual relationship map. Colour = type of entity (person, phone, account, "
         "vehicle...). A red ring means that entity is deliberately excluded from every ranking below "
         "(an investigating officer's own phone, or a customer-care number) so it never wrongly looks "
         "like a suspect. Click any dot to see the exact FIR text, call records or transactions behind it."),
        ("Leads", "Every pattern the system found, in plain language, with the reasoning and the exact "
         "source record IDs attached. An investigator marks each one Useful / Already Known / Wrong "
         "Person -- the system never closes this loop itself."),
        ("Review Queue", "Cases where two mentions of a similar name could NOT be confirmed as the same "
         "person from the records alone. The system deliberately refuses to guess here and asks a human "
         "instead."),
        ("Women Safety (flagship)", "The trafficking-network view: recruiter and transporter candidates, "
         "and a repeated-location signal (the same real place named in several independent reports). "
         "This reuses the exact same detection machinery as the financial-fraud view -- point this out, "
         "it is the single strongest technical claim in the whole system."),
        ("Self-Evaluation", "The system grading its own work: which planted test scenarios it caught, "
         "how confident its text-extraction is, and an honestly-reported (not inflated) accuracy number "
         "for its most experimental feature, missing-link recovery."),
        ("Audit Chain", "Every query and decision, permanently chained with cryptographic hashes so "
         "tampering is detectable. As admin, there's a live demo button that deliberately corrupts one "
         "entry and shows both the server and the browser independently catching it, then restores it."),
    ]
    for i, (title, txt) in enumerate(steps, start=1):
        story.append(StepRow(i, title, txt, doc.width))
        story.append(Spacer(1, 8))
    story.append(PageBreak())

    # ---------------- Real world case 1 ----------------
    story.append(eyebrow("Real-World Validation - Financial Networks"))
    story.append(h1("This Mirrors an Actual CBI Operation"))
    story.append(body(
        "The demo data is entirely synthetic (fabricated names and numbers, generated for this "
        "presentation) -- but the pattern it is built to catch is not hypothetical. CBI's Operation "
        "Chakra-VI, a coordinated raid across 89 locations in 20 states on 4 September 2026, arrested "
        "three people playing exactly the three roles our mule-layering detector is built to separate:"
    ))
    story.append(data_table(
        ["Real role (Operation Chakra-VI)", "Maps to our system"],
        [
            ["Akash (Haryana) - received Rs. 1.95 crore", "A fan-in / layer-1 account absorbing funds from many senders"],
            ["Raja Karmakar (Kolkata) - \"routed Rs. 1.5 crore through his firm's account\" (layering)", "The layer-2 consolidation account our recursion-depth scoring flags"],
            ["Jyoti Rani - withdrew and transferred the funds", "The cash-out endpoint at the end of the chain"],
        ],
        col_widths=[92 * mm, 78 * mm],
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        '"the CBI arrested three persons allegedly involved in receiving, layering and dispersing fraud '
        'proceeds" -- Coin Edition, 5 September 2026',
        styles["QuoteText"]
    ))
    story.append(Spacer(1, 6))
    story.append(body(
        "The same investigation traces back to three underlying \"digital arrest\" cases worth "
        "Rs. 42.36 crore combined, and a separate CBI release from August 2025 explicitly used the word "
        "\"kingpin\" for the syndicate's head, arrested trying to board a flight out of the country -- "
        "which is precisely the framing this system's PageRank and broker-scoring are built around: "
        "surfacing the person who matters, not just the account with the most transactions."
    ))
    story.append(Paragraph(
        "Sources: Coin Edition, \"Indian CBI Raids 89 Locations Across 20 States Under Operation "
        "Chakra-VI\" (5 Sep 2026) -- coinedition.com. News On Air / Akashvani (Prasar Bharati), \"CBI "
        "Arrests Kingpin of Transnational Cyber Fraud Syndicate Under Operation Chakra\" (25 Aug 2025) "
        "and \"Operation Chakra-V: CBI Cracks Down on Cyber Fraud Network\" (26 Jun 2025) -- newsonair.gov.in.",
        styles["Caption"]
    ))
    story.append(PageBreak())

    # ---------------- Real world case 2 ----------------
    story.append(eyebrow("Real-World Validation - Trafficking Networks"))
    story.append(h1("This Mirrors an Actual Delhi Police / J&amp;K Police Case"))
    story.append(body(
        "On 14 and 19 August 2025, Delhi Police's Anti-Human Trafficking Unit, working with J&amp;K Police, "
        "dismantled a network trafficking an estimated 500 people over two years for bonded domestic "
        "labour. The roles investigators identified map directly onto our Recruiter -> Transporter -> "
        "Receiver detection chain:"
    ))
    story.append(data_table(
        ["Real role (Delhi/Srinagar case)", "Maps to our system"],
        [
            ["Salim-ul-Rehman alias Wasim - ran the agency (\"V.A. Manpower Pvt. Ltd.\"), Ganderbal, Srinagar", "RECRUITER: the recruiter fan-out heuristic"],
            ["Suraj - \"transporting trafficked victims at the behest of Delhi-based agents\" from Old Delhi Railway Station", "TRANSPORTER: the structural bridge-path detector (one foot in the recruiter's contacts, one foot in a denser cluster on the other side)"],
            ["Md. Talib &amp; Satnam Singh alias \"Sardar Ji\" - arrested at the Srinagar end", "RECEIVER-side cluster"],
        ],
        col_widths=[92 * mm, 78 * mm],
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        '"Suraj allegedly admitted he ferried trafficked persons from railway stations in Delhi on the '
        'instructions of agents" -- Hindustan Times, 28 August 2025',
        styles["QuoteText"]
    ))
    story.append(Spacer(1, 6))
    story.append(body(
        "Two details in this real case are especially close to features built into this system: victims "
        "were consistently recruited from the <b>same physical location</b> (Old Delhi Railway Station) "
        "across multiple, independent police accounts -- exactly the repeated-location signal the "
        "Women-Safety view surfaces. And the case was cracked using <b>technical and manual "
        "surveillance</b> -- which is why this system now ingests surveillance reports and "
        "intelligence-agency reports as their own first-class data sources, not just FIRs."
    ))
    story.append(Paragraph(
        "Sources: ANI, \"Delhi Police busts human trafficking racket, 4 arrested\" (28 Aug 2025) -- "
        "aninews.in. Hindustan Times, \"Delhi Police busts interstate trafficking network in Srinagar\" "
        "(28 Aug 2025) -- hindustantimes.com.",
        styles["Caption"]
    ))
    story.append(PageBreak())

    # ---------------- Q&A ----------------
    story.append(eyebrow("Anticipated Questions"))
    story.append(h1("If You're Asked..."))
    qa = [
        ("\"Is this trained on real case data?\"",
         "No. Every name, number and record in the demo is synthetic, generated for this presentation. "
         "The patterns it detects (mule layering, burner-SIM rotation, recruiter-transporter chains) are "
         "documented, well-known tactics -- validated against the real Operation Chakra-VI and Delhi/"
         "Srinagar cases on the previous two pages -- but no real person's data is in this system."),
        ("\"Does the AI decide who's guilty?\"",
         "No, by design. Every output is called a Lead, never a verdict, and every lead requires a human "
         "disposition (Useful / Already Known / Wrong Person) before it goes anywhere. Show the Leads tab."),
        ("\"What stops it from being wrong?\"",
         "Nothing stops any detector from producing a false positive -- and it's built to be transparent "
         "about that rather than hide it. The Women-Safety recruiter heuristic, for example, is "
         "deliberately generic and will also flag a burner-rotation phone; every candidate is marked as "
         "needing verification for exactly this reason. The Self-Evaluation tab shows this honestly, "
         "including a low single-digit-percent recall number for its hardest, most experimental feature "
         "(missing-link recovery) -- that number was not adjusted to look better."),
        ("\"Is this blockchain?\"",
         "The audit trail uses the same core idea blockchains use for tamper-evidence -- a chain of "
         "cryptographic hashes where changing any past entry breaks every hash after it -- verified "
         "independently by the server and the browser. It is not a distributed ledger, because a single "
         "agency's system of record doesn't need one; the integrity guarantee is the same."),
        ("\"What happens to someone wrongly flagged?\"",
         "Nothing happens to them automatically. A flagged entity is data on a screen an investigator "
         "reviews; there is no automated action of any kind (no account freeze, no notification, no "
         "record change) tied to any detector firing."),
    ]
    for q, a in qa:
        story.append(Paragraph(f"<b>{q}</b>", styles["Body"]))
        story.append(Paragraph(a, styles["StepBody"]))
        story.append(Spacer(1, 8))

    doc.build(story, canvasmaker=FooterCanvas)
    print(f"Wrote {os.path.abspath(OUT_PATH)}")


if __name__ == "__main__":
    build()
