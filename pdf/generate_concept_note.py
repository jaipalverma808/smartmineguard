"""
SmartMineGuard - Official Technical & Enforcement Concept Note PDF Generator
Prepared for: Mining & Mineral Enforcement Authorities
Document: SmartMineGuard_Enforcement_Concept_Note.pdf
Exact Length: 8 Pages (A4 Portrait)
Design: Clean, Administrative, Professional, High Table Density, Zero AI Gimmicks
"""

import os
import sys
from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether, PageBreak
)
from reportlab.pdfgen import canvas

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "pdf" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_PDF = OUTPUT_DIR / "SmartMineGuard_Enforcement_Concept_Note.pdf"
WORKSPACE_PDF = Path("D:/mail pdf/SmartMineGuard_Enforcement_Concept_Note.pdf")


class ConceptNoteCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and print 'Page X of Y'
    and formal running administrative headers and footers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        if self._pageNumber == 1:
            return  # Suppress running header/footer on cover page

        self.saveState()
        
        # Running Top Header
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#0F3826"))  # Deep Forest Green
        self.drawString(38, 810, "SMARTMINEGUARD")
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#475569"))
        self.drawString(135, 810, "— Mining Transport Surveillance & Anti-Fraud Control System")
        self.drawRightString(557, 810, "ENFORCEMENT CONCEPT NOTE")
        
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.6)
        self.line(38, 804, 557, 804)

        # Running Bottom Footer
        self.line(38, 42, 557, 42)
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor("#0F3826"))
        self.drawString(38, 30, "STATUTORY ENFORCEMENT & MONITORING SUPPORT")
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(255, 30, "Deterministic Rule Governance • Explainable Audit Trail")
        self.drawRightString(557, 30, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def build_concept_note_pdf():
    print("[*] Generating SmartMineGuard Official Enforcement Concept Note PDF...")

    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=A4,
        leftMargin=38,
        rightMargin=38,
        topMargin=44,
        bottomMargin=46
    )

    styles = getSampleStyleSheet()

    # Administrative Color Palette
    c_primary = colors.HexColor("#0F3826")      # Deep Administrative Forest Green
    c_secondary = colors.HexColor("#1E3A8A")    # Deep Navy Blue
    c_dark = colors.HexColor("#0F172A")         # Slate Dark Charcoal
    c_sub = colors.HexColor("#475569")          # Slate 600
    c_card_bg = colors.HexColor("#F8FAFC")      # Slate 50
    c_border = colors.HexColor("#CBD5E1")       # Slate 300
    c_alert = colors.HexColor("#991B1B")        # Crimson Alert Red

    # Custom Typography Styles
    cover_sup_style = ParagraphStyle(
        "CoverSup",
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#D4AF37"),
        alignment=1
    )

    cover_title_style = ParagraphStyle(
        "CoverTitle",
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=colors.white,
        alignment=1
    )

    cover_sub_style = ParagraphStyle(
        "CoverSub",
        fontName="Helvetica",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#E2E8F0"),
        alignment=1
    )

    cover_scope_style = ParagraphStyle(
        "CoverScope",
        fontName="Helvetica-Oblique",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#CBD5E1"),
        alignment=1
    )

    h1_style = ParagraphStyle(
        "H1_Admin",
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=c_primary,
        spaceBefore=0,
        spaceAfter=4,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        "H2_Admin",
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=c_dark,
        spaceBefore=5,
        spaceAfter=2.5,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        "Body_Admin",
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=2,
        spaceAfter=2
    )

    body_bold = ParagraphStyle(
        "Body_Bold",
        parent=body_style,
        fontName="Helvetica-Bold"
    )

    bullet_style = ParagraphStyle(
        "Bullet_Admin",
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#334155"),
        leftIndent=10,
        spaceBefore=1.5,
        spaceAfter=1.5
    )

    tbl_header = ParagraphStyle(
        "TblHeader",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=0
    )

    tbl_cell = ParagraphStyle(
        "TblCell",
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#1E293B")
    )

    tbl_cell_bold = ParagraphStyle(
        "TblCellBold",
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#0F172A")
    )

    tbl_cell_alert = ParagraphStyle(
        "TblCellAlert",
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=c_alert
    )

    def make_divider():
        return HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#CBD5E1"), spaceBefore=4, spaceAfter=6)

    def make_callout(text, title="IMPORTANT NOTICE", border_col="#0F3826", bg_col="#ECFDF5", text_col="#065F46"):
        title_p = Paragraph(f"<b>{title}:</b> {text}", ParagraphStyle(
            "CInner", fontName="Helvetica", fontSize=8, leading=11, textColor=colors.HexColor(text_col)
        ))
        t = Table([[title_p]], colWidths=[518])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(bg_col)),
            ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor(border_col)),
            ('TOPPADDING', (0, 0), (-1, -1), 4.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        return t

    story = []

    # =========================================================================
    # PAGE 1: COVER + EXECUTIVE SUMMARY
    # =========================================================================
    top_notice = Table([[
        Paragraph("<font size=7.5 color='#475569'><b>OFFICIAL ENFORCEMENT CONCEPT NOTE • TECHNICAL BRIEFING DOCUMENT</b></font>", ParagraphStyle("P1Top", alignment=0)),
        Paragraph("<font size=7.5 color='#0F3826'><b>DOC REF: SMG-CN-2026-ENF</b></font>", ParagraphStyle("P1Ref", alignment=2))
    ]], colWidths=[360, 158])
    top_notice.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(top_notice)
    story.append(HRFlowable(width="100%", thickness=1, color=c_primary, spaceBefore=1, spaceAfter=5))

    # Main Title Block
    title_data = [
        [Paragraph("STATUTORY SURVEILLANCE &amp; DISPATCH RECONCILIATION", cover_sup_style)],
        [Spacer(1, 1)],
        [Paragraph("SMARTMINEGUARD", cover_title_style)],
        [Spacer(1, 1)],
        [Paragraph("<b>Mining &amp; Mineral Transport Monitoring and Anti-Fraud Control System</b>", cover_sub_style)],
        [Spacer(1, 2)],
        [Paragraph("\"Data-driven dispatch reconciliation, GPS surveillance and explainable rule-based enforcement support.\"", cover_scope_style)],
    ]
    title_table = Table(title_data, colWidths=[518])
    title_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_primary),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('BOX', (0, 0), (-1, -1), 1.2, colors.HexColor("#D4AF37")),
    ]))
    story.append(title_table)
    story.append(Spacer(1, 5))

    # Metadata Strip Table
    meta_rows = [
        [
            Paragraph("<b>Prepared For:</b>", tbl_cell_bold),
            Paragraph("Mining &amp; Mineral Enforcement Authorities / Directorate of Mines &amp; Geology", tbl_cell),
            Paragraph("<b>Date of Issue:</b>", tbl_cell_bold),
            Paragraph(datetime.now().strftime("%d %B %Y"), tbl_cell)
        ],
        [
            Paragraph("<b>Prepared By:</b>", tbl_cell_bold),
            Paragraph("SmartMineGuard Student Development Team (Project Prototype)", tbl_cell),
            Paragraph("<b>Architecture:</b>", tbl_cell_bold),
            Paragraph("Deterministic Software (Zero AI/ML)", tbl_cell)
        ],
        [
            Paragraph("<b>Document Purpose:</b>", tbl_cell_bold),
            Paragraph("High-Level Operational &amp; Technical Enforcement Concept Note", tbl_cell),
            Paragraph("<b>Legal Scope:</b>", tbl_cell_bold),
            Paragraph("Decision-Support Tool under MMDR Act Sec 21", tbl_cell)
        ]
    ]
    meta_table = Table(meta_rows, colWidths=[95, 230, 85, 108])
    meta_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor("#F1F5F9")),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 5))

    # Sources 2-column table inside executive summary
    src_left = Paragraph(
        "• <b>Mine / Lease Records:</b> Concession boundaries &amp; limits<br/>"
        "• <b>Commercial Trucks:</b> Registration &amp; tare weights<br/>"
        "• <b>Commercial Drivers:</b> Transporter profiles &amp; logs<br/>"
        "• <b>e-Rawaana Permits:</b> Authorized tonnage &amp; QR hashes<br/>"
        "• <b>GPS / AIS-140:</b> Live breadcrumbs &amp; velocity pings",
        bullet_style
    )
    src_right = Paragraph(
        "• <b>Automated Weighbridges:</b> Pithead gross, tare, net<br/>"
        "• <b>Spatial Geofences:</b> Lease boundary &amp; transit buffers<br/>"
        "• <b>Destinations:</b> Registered crushers &amp; stockyards<br/>"
        "• <b>Corridor Checkpoints:</b> Toll &amp; border monitoring booths<br/>"
        "• <b>Mass-Balance Ledgers:</b> Production vs dispatch stock",
        bullet_style
    )
    sources_split = Table([[src_left, src_right]], colWidths=[250, 250])
    sources_split.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    # Executive Summary Box
    exec_content = [
        [Paragraph("<b>EXECUTIVE SUMMARY &amp; PLATFORM OBJECTIVE</b>", ParagraphStyle("ExH", fontName="Helvetica-Bold", fontSize=8.5, textColor=c_primary))],
        [Paragraph(
            "<b>SmartMineGuard</b> is a software prototype designed to bring together and authoritatively cross-reference "
            "disparate data streams generated across the mineral transportation supply chain. In conventional operations, "
            "data is captured in unlinked silos—mine lease records, vehicle registries, driver rosters, e-Rawaana transit permits, "
            "AIS-140 GPS feeds, pithead weighbridge receipts, destination receipts, and quarry production stock ledgers. "
            "Because these systems rarely talk to one another in real time, fraudulent practices such as transit pass recycling, "
            "deliberate overloading, unpermitted route diversions, and clandestine extraction go undetected until audit months later.",
            body_style
        )],
        [Spacer(1, 2)],
        [Paragraph("<b>Ten Information Streams Integrated &amp; Connected by SmartMineGuard:</b>", ParagraphStyle("SrcH", fontName="Helvetica-Bold", fontSize=7.5, textColor=c_secondary))],
        [sources_split],
        [Spacer(1, 2)],
        [Paragraph(
            "The system evaluates these records continuously using <b>deterministic, explainable mathematical and spatial rules</b>. "
            "When anomalies occur, the platform generates instant statutory alerts and compiles structured evidence dossiers for field squads.",
            body_style
        )]
    ]
    exec_table = Table(exec_content, colWidths=[518])
    exec_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_card_bg),
        ('BOX', (0, 0), (-1, -1), 0.8, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 4.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(exec_table)
    story.append(Spacer(1, 4))

    # Core Philosophy Box
    philosophy_box = make_callout(
        "\"SmartMineGuard is a software-based monitoring and reconciliation platform designed to cross-check mining "
        "transportation data and flag potentially irregular mineral trips for officer verification.\"<br/><br/>"
        "<b>Statutory Operational Flow:</b><br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;<b>SYSTEM DETECTS &amp; FLAGS</b> &nbsp;⟶&nbsp; "
        "<b>OFFICER REVIEWS</b> &nbsp;⟶&nbsp; "
        "<b>OFFICER VERIFIES</b> &nbsp;⟶&nbsp; "
        "<b>ACTION UNDER APPLICABLE RULES</b><br/>"
        "<i>Crucial Notice: SmartMineGuard does NOT claim to independently prove offences or replace human judgment. "
        "The enforcement officer remains the sole statutory authority and legal decision-maker under Section 21 of the MMDR Act.</i>",
        title="CORE STATUTORY PRINCIPLE",
        border_col="#1E3A8A", bg_col="#EFF6FF", text_col="#1E40AF"
    )
    story.append(philosophy_box)

    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: THE PROBLEM
    # =========================================================================
    story.append(Paragraph("1. WHY MINERAL TRANSPORT REQUIRES CROSS-CHECKING", h1_style))
    story.append(make_divider())

    story.append(Paragraph(
        "Commercial mineral transit is an intensive, multi-step operational sequence spanning quarry extraction pits, "
        "weighment platforms, state highways, regional checkpoints, and commercial processing facilities. "
        "Because each step is managed by different entities using disparate tools (manual gate registers, digital scale indicators, "
        "independent GPS dashboards, paper permits), critical operational irregularities frequently slip through unseen.",
        body_style
    ))
    story.append(Spacer(1, 4))

    # Linear Disconnected Workflow Table (8 Columns, clean width)
    flow_diagram = [
        [
            Paragraph("<b>1. PERMIT</b><br/><font size=6 color='#64748B'>e-Rawaana</font>", ParagraphStyle("F1", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
            Paragraph("<b>2. TRUCK</b><br/><font size=6 color='#64748B'>Carrier</font>", ParagraphStyle("F2", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
            Paragraph("<b>3. ENTRY</b><br/><font size=6 color='#64748B'>Geofence</font>", ParagraphStyle("F3", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
            Paragraph("<b>4. LOADING</b><br/><font size=6 color='#64748B'>Pithead</font>", ParagraphStyle("F4", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
            Paragraph("<b>5. SCALE</b><br/><font size=6 color='#64748B'>Gross/Tare</font>", ParagraphStyle("F5", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
            Paragraph("<b>6. DISPATCH</b><br/><font size=6 color='#64748B'>Gate Exit</font>", ParagraphStyle("F6", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
            Paragraph("<b>7. GPS</b><br/><font size=6 color='#64748B'>Transit</font>", ParagraphStyle("F7", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
            Paragraph("<b>8. RECEIPT</b><br/><font size=6 color='#64748B'>Destination</font>", ParagraphStyle("F8", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
        ]
    ]
    t_flow = Table(flow_diagram, colWidths=[65, 65, 65, 65, 65, 65, 65, 63])
    t_flow.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(t_flow)
    story.append(Spacer(1, 4))

    disconnection_callout = make_callout(
        "\"If these events are recorded separately in disconnected registers or standalone databases, "
        "irregularities can be exceptionally difficult to identify in real time. "
        "SmartMineGuard connects them into one single, auditable trip entity.\"",
        title="THE RECONCILIATION IMPERATIVE",
        border_col="#D97706", bg_col="#FFFBEB", text_col="#B45309"
    )
    story.append(disconnection_callout)
    story.append(Spacer(1, 5))

    story.append(Paragraph("<b>Five Critical Operational Vulnerabilities Addressed:</b>", h2_style))

    # Structured Table of the 5 Problems
    problem_rows = [
        [
            Paragraph("<b>Operational Vulnerability</b>", tbl_header),
            Paragraph("<b>How the Irregularity Occurs</b>", tbl_header),
            Paragraph("<b>Consequence &amp; Enforcement Risk</b>", tbl_header)
        ],
        [
            Paragraph("<b>1. Vehicle Overloading &amp; Tare Inflation</b>", tbl_cell_bold),
            Paragraph("Tipper trucks are loaded beyond authorized e-Rawaana limits or vehicle RTO axle capacity. Drivers tamper with empty tare weight (using false water ballast or off-scale tire parking) to conceal extra cargo.", tbl_cell),
            Paragraph("Extensive road and bridge degradation, evasion of statutory mineral royalty, and severe traffic hazards on commercial highway corridors.", tbl_cell)
        ],
        [
            Paragraph("<b>2. e-Rawaana Recycling (\"Parchi Reuse\")</b>", tbl_cell_bold),
            Paragraph("A legitimate digital transit pass is reused for multiple unbilled trips between quarry and crusher before the expiry window elapses, because delivery confirmation is not synchronized.", tbl_cell),
            Paragraph("Loss of state royalty revenue; multiple truckloads of mineral transit illegally under the legal cover of a single paid pass.", tbl_cell)
        ],
        [
            Paragraph("<b>3. Unauthorized Route Diversion</b>", tbl_cell_bold),
            Paragraph("Commercial carriers depart from legal highway transit corridors into unapproved rural links, private crusher bypasses, or prohibited riverbed extraction zones.", tbl_cell),
            Paragraph("Unaccounted dumping, mineral theft, and unmonitored extraction from eco-sensitive buffer zones and forest reservations.", tbl_cell)
        ],
        [
            Paragraph("<b>4. GPS Blackouts &amp; Telemetry Tampering</b>", tbl_cell_bold),
            Paragraph("AIS-140 GPS transponders are deliberately disconnected, wire-cut to internal battery, or jammed using portable RF jamming devices while traversing sensitive routes.", tbl_cell),
            Paragraph("Total loss of telematic visibility during active haulage, concealing unpermitted loading or illicit detour routes.", tbl_cell)
        ],
        [
            Paragraph("<b>5. Pithead Production vs. Dispatch Mismatch</b>", tbl_cell_bold),
            Paragraph("Quarry leaseholders dispatch mineral tonnages far exceeding their sanctioned annual environmental clearance quotas or report inaccurate stockpile figures.", tbl_cell),
            Paragraph("Unregulated over-extraction, depletion of natural reserves beyond legal concession limits, and fraudulent mass-balance reporting.", tbl_cell)
        ]
    ]
    t_problem = Table(problem_rows, colWidths=[130, 218, 170])
    t_problem.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(t_problem)
    story.append(Spacer(1, 5))

    story.append(Paragraph(
        "<b>The Need for Multi-Source Reconciliation:</b> No single data point—whether a weighment slip or a GPS coordinate—is "
        "sufficient to confirm statutory compliance. Only by dynamically binding the vehicle, permit, scale weights, and "
        "continuous spatial telemetry into a unified audit trail can enforcement squads detect anomalies with certainty.",
        body_style
    ))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 3: HOW DATA IS STORED AND CONNECTED
    # =========================================================================
    story.append(Paragraph("2. HOW SMARTMINEGUARD CONNECTS THE DATA", h1_style))
    story.append(make_divider())

    story.append(Paragraph(
        "SmartMineGuard transforms disconnected administrative logs into a unified, relational trip entity. "
        "Instead of reviewing tables in isolation, the platform links every physical movement to an unbroken digital chain of custody.",
        body_style
    ))
    story.append(Spacer(1, 3))

    # Conceptual Architecture Box Diagram (No Unicode arrows, pure clean reportlab)
    arch_diagram = [
        [Paragraph("<b>SMARTMINEGUARD INTEGRATED SURVEILLANCE PLATFORM</b>", ParagraphStyle("ArchHead", alignment=1, fontName="Helvetica-Bold", fontSize=9, textColor=colors.white))],
        [Paragraph(
            "<font size=6.5 color='#475569'>PRIMARY INGESTION ENTITIES (REAL-TIME SENSORS &amp; REGISTRIES)</font><br/>"
            "<b>[ MINE LEASE ]</b> &nbsp;&nbsp;&nbsp;&nbsp; "
            "<b>[ VEHICLE / TRUCK ]</b> &nbsp;&nbsp;&nbsp;&nbsp; "
            "<b>[ e-RAWAANA PERMIT ]</b> &nbsp;&nbsp;&nbsp;&nbsp; "
            "<b>[ AIS-140 GPS ]</b> &nbsp;&nbsp;&nbsp;&nbsp; "
            "<b>[ WEIGHBRIDGE SCALE ]</b>",
            ParagraphStyle("ArchL1", alignment=1, fontName="Helvetica", fontSize=8, textColor=c_dark)
        )],
        [Paragraph("|", ParagraphStyle("DArr", alignment=1, fontSize=8, textColor=c_primary))],
        [Paragraph(
            "<b>UNIFIED TRANSIT TRIP CYCLE (Single Auditable Entity)</b><br/>"
            "<font size=7 color='#64748B'>Binds Truck Registration + Permit Number + Tare/Gross Weights + Driver + Mine Timestamps</font>",
            ParagraphStyle("ArchL2", alignment=1, fontName="Helvetica-Bold", fontSize=8.5, textColor=c_primary)
        )],
        [Paragraph("|", ParagraphStyle("DArr", alignment=1, fontSize=8, textColor=c_primary))],
        [Paragraph(
            "<font size=6.5 color='#475569'>CONTINUOUS SPATIAL &amp; MASS-BALANCE AUDIT</font><br/>"
            "<b>[ Destination Verification ]</b> &nbsp;&nbsp;•&nbsp;&nbsp; "
            "<b>[ Checkpoint Crossings ]</b> &nbsp;&nbsp;•&nbsp;&nbsp; "
            "<b>[ Pithead Stock Mass-Balance ]</b>",
            ParagraphStyle("ArchL3", alignment=1, fontName="Helvetica", fontSize=8, textColor=c_dark)
        )],
        [Paragraph("|", ParagraphStyle("DArr", alignment=1, fontSize=8, textColor=c_primary))],
        [Paragraph(
            "<b>DETERMINISTIC CROSS-CHECK &amp; STATUTORY DETECTION RULES</b><br/>"
            "<font size=7 color='#64748B'>Evaluates 11 Mathematical &amp; Spatial Constraints • Computes 0–100 Explainable Risk Score</font>",
            ParagraphStyle("ArchL4", alignment=1, fontName="Helvetica-Bold", fontSize=8.5, textColor=c_secondary)
        )],
        [Paragraph("|", ParagraphStyle("DArr", alignment=1, fontSize=8, textColor=c_primary))],
        [Paragraph(
            "<b>ACTIONABLE STATUTORY ALERT &amp; SQUAD TRIAGE</b><br/>"
            "<font size=7 color='#64748B'>Surfaces in Officer Enforcement Console • Ranked by Severity (Low, Medium, High, Critical)</font>",
            ParagraphStyle("ArchL5", alignment=1, fontName="Helvetica-Bold", fontSize=8.5, textColor=c_alert)
        )],
        [Paragraph("|", ParagraphStyle("DArr", alignment=1, fontSize=8, textColor=c_primary))],
        [Paragraph(
            "<b>OFFICER FIELD VERIFICATION &amp; EVIDENCE DOSSIER PDF</b><br/>"
            "<font size=7 color='#64748B'>Roadside QR Scan • On-Site Physical Inspection • Section 21 MMDR Statutory Case Dossier</font>",
            ParagraphStyle("ArchL6", alignment=1, fontName="Helvetica-Bold", fontSize=8.5, textColor=c_primary)
        )]
    ]
    t_arch = Table(arch_diagram, colWidths=[518])
    t_arch.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#F8FAFC")),
        ('BOX', (0, 0), (-1, -1), 0.8, c_border),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2),
    ]))
    story.append(t_arch)
    story.append(Spacer(1, 5))

    story.append(Paragraph("<b>The Connected Journey Representation (Conceptual Example):</b>", h2_style))
    story.append(Paragraph(
        "Each physical haulage movement is modeled as an interconnected chain of certified data points. "
        "Consider an illustrative dispatch cycle:",
        body_style
    ))
    story.append(Spacer(1, 2))

    journey_points = [
        [
            Paragraph("<b>Asset / Parameter</b>", tbl_header),
            Paragraph("<b>Captured Value</b>", tbl_header),
            Paragraph("<b>Verification Mechanism &amp; Cross-Check Role</b>", tbl_header)
        ],
        [
            Paragraph("Vehicle Identification", tbl_cell_bold),
            Paragraph("HR26AB1234 (10-Wheeler Tipper)", tbl_cell),
            Paragraph("Cross-referenced against RTO unladen tare weight baselines and registered fleet database.", tbl_cell)
        ],
        [
            Paragraph("Statutory Transit Pass", tbl_cell_bold),
            Paragraph("e-Rawaana SMG-2026-00125", tbl_cell),
            Paragraph("Locked to single transit cycle; checks mineral classification, buyer, and active validity window.", tbl_cell)
        ],
        [
            Paragraph("Mine Concession &amp; Gate", tbl_cell_bold),
            Paragraph("Aravalli Quarry Block A (08:12 Entry)", tbl_cell),
            Paragraph("Geofence triggers automated mine arrival; matches active permit; initializes trip counter.", tbl_cell)
        ],
        [
            Paragraph("Automated Scale Weighment", tbl_cell_bold),
            Paragraph("Gross: 35.8 MT | Tare: 11.2 MT", tbl_cell),
            Paragraph("M2M scale capture; derives net payload (24.6 MT); evaluates overload vs. permit (24.0 MT).", tbl_cell)
        ],
        [
            Paragraph("Outbound Dispatch Gate", tbl_cell_bold),
            Paragraph("08:42 Mine Exit Clearance", tbl_cell),
            Paragraph("Geofence exit authorizes dispatch; increments daily commercial trip round counter.", tbl_cell)
        ],
        [
            Paragraph("GPS Route Tracking", tbl_cell_bold),
            Paragraph("NH-48 Designated Transit Corridor", tbl_cell),
            Paragraph("Calculates perpendicular cross-track deviation from polyline axis in real time.", tbl_cell)
        ],
        [
            Paragraph("Destination Delivery", tbl_cell_bold),
            Paragraph("Bhiwadi Crushing Zone", tbl_cell),
            Paragraph("Destination geofence arrival auto-consumes e-Rawaana; locks permit against reuse.", tbl_cell)
        ]
    ]
    t_journey = Table(journey_points, colWidths=[120, 160, 238])
    t_journey.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(t_journey)
    story.append(Spacer(1, 4))

    story.append(Paragraph(
        "<b>The Enforcement Advantage:</b> By evaluating data as a connected sequence, the system detects discrepancies "
        "that are invisible in single-source audits. For example, a truck cannot present a valid weighment slip without an "
        "associated mine entry geofence event, nor can it claim transit completion without traversing designated highway checkpoints.",
        body_style
    ))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 4: FIVE MAJOR ANTI-FRAUD CONTROLS
    # =========================================================================
    story.append(Paragraph("3. FIVE MAJOR CONTROL MECHANISMS", h1_style))
    story.append(make_divider())

    story.append(Paragraph(
        "SmartMineGuard enforces statutory compliance through <b>deterministic, explainable mathematical and spatial rules</b>. "
        "The system strictly avoids opaque AI/ML predictions. Every control mechanism produces a concrete, auditable metric.",
        body_style
    ))
    story.append(Spacer(1, 3))

    # Control 1
    story.append(Paragraph("<b>CONTROL 1 — AUTOMATED WEIGHBRIDGE CONTROL (Net = Gross - Tare)</b>", h2_style))
    story.append(Paragraph(
        "In physical operations, net payload weight is calculated directly via automated Machine-to-Machine (M2M) telemetry: "
        "<b>Gross Weight - Tare Weight = Net Mineral Payload</b>. "
        "Operators cannot type or alter the net tonnage manually. If a manual override is required (e.g. scale calibration), "
        "it requires authorized supervisor authentication, documented justification, and generates an audit log entry.<br/>"
        "• <i>Illustrative Check:</i> Gross = 35.8 MT, Tare = 11.2 MT ⟶ Net = 24.6 MT. Permitted = 24.0 MT. "
        "Excess = <b>+0.6 MT</b> (+2.5% variance flagged).",
        body_style
    ))
    story.append(Spacer(1, 2.5))

    # Control 2
    story.append(Paragraph("<b>CONTROL 2 — GPS GEOFENCING &amp; ROUTE CORRIDOR DEVIATION (&gt;500m Threshold)</b>", h2_style))
    story.append(Paragraph(
        "Quarry concession perimeters are monitored via spatial geofences that automatically record vehicle arrival and departure timestamps. "
        "During highway haulage, real-time GPS breadcrumbs are cross-checked against authorized polyline transit corridors.<br/>"
        "• <i>Documented Rule:</i> If a transport vehicle deviates more than <b>500 metres perpendicular distance</b> from the "
        "designated corridor axis, a <b>ROUTE DEVIATION</b> alert is raised with exact coordinates and departure distance.",
        body_style
    ))
    story.append(Spacer(1, 2.5))

    # Control 3
    story.append(Paragraph("<b>CONTROL 3 — e-RAWAANA RECONCILIATION &amp; PERMIT REUSE PREVENTION</b>", h2_style))
    story.append(Paragraph(
        "Transit permits follow a strict, irreversible five-stage operational lifecycle: "
        "<b>ISSUED ⟶ TRUCK ARRIVED ⟶ WEIGHED ⟶ DISPATCHED ⟶ COMPLETED / CONSUMED</b>.<br/>"
        "• <i>Pass Recycling Prevention:</i> Each e-Rawaana is cryptographically locked to a single active trip cycle. "
        "Once marked CONSUMED at destination, any attempt to initiate a second dispatch on the same permit raises a "
        "<b>CRITICAL PERMIT REUSE</b> alert.<br/>"
        "• <i>Vehicle-Permit Binding:</i> Flags an immediate mismatch alert if the physical vehicle registration does not match the permit.",
        body_style
    ))
    story.append(Spacer(1, 2.5))

    # Control 4
    story.append(Paragraph("<b>CONTROL 4 — GPS SIGNAL BLACKOUT MONITORING (&gt;15 Minutes Anomaly)</b>", h2_style))
    story.append(Paragraph(
        "The system continuously audits the heartbeat stream of AIS-140 telematic units during active transit trips.<br/>"
        "• <i>Documented Rule:</i> If GPS pings cease for <b>more than 15 consecutive minutes</b> while a trip is in transit, "
        "the platform flags a <b>GPS BLACKOUT</b> alert, recording the last known coordinates, heading, and subsequent restoration time.<br/>"
        "• <i>Statutory Clarity:</i> <b>A blackout is treated as an operational anomaly requiring officer review and physical verification, "
        "not as automatic proof of illegal activity.</b> (E.g. distinguishing benign mountain cellular dead zones from tampering).",
        body_style
    ))
    story.append(Spacer(1, 2.5))

    # Control 5
    story.append(Paragraph("<b>CONTROL 5 — PRODUCTION / DISPATCH MASS-BALANCE RECONCILIATION</b>", h2_style))
    story.append(Paragraph(
        "At the quarry pithead, extraction stockpiles are governed by the fundamental law of conservation of mass: "
        "<b>Expected Closing Stock = Opening Stock + Today's Production - Today's Dispatched</b>.<br/>"
        "• <i>Documented Rule:</i> If physically recorded closing stock differs from expected closing stock beyond the "
        "statutory <b>50 MT configured tolerance</b>, the system raises a <b>PRODUCTION-DISPATCH MISMATCH</b> alert.<br/>"
        "• <i>Illustrative Check:</i> Opening = 1,250 MT + Blasting = 500 MT - Dispatched = 420 MT ⟶ Expected = 1,330 MT. "
        "If recorded stock is 1,410 MT (80 MT variance), an immediate investigation alert is triggered.",
        body_style
    ))
    story.append(Spacer(1, 4))

    control_summary = make_callout(
        "All 5 controls execute in automated sequence. By removing human manual data entry at scale gates and highway corridors, "
        "the platform ensures that records reflect physical reality, giving enforcement squads dependable, verifiable data.",
        title="CONTROL INTEGRITY",
        border_col="#0F3826", bg_col="#F0FDF4", text_col="#166534"
    )
    story.append(control_summary)

    story.append(PageBreak())

    # =========================================================================
    # PAGE 5: FROM DATA TO OFFICER ALERT
    # =========================================================================
    story.append(Paragraph("4. FROM DATA TO ACTIONABLE OFFICER ALERT", h1_style))
    story.append(make_divider())

    story.append(Paragraph(
        "SmartMineGuard does not generate ambiguous 'AI risk scores' or unexplainable predictions. "
        "Instead, every alert follows a transparent, multi-stage processing pipeline grounded in statutory rules.",
        body_style
    ))
    story.append(Spacer(1, 3))

    # Visual Pipeline Table (7 Steps, 74 width each = 518 pt)
    pipe_data = [
        [
            Paragraph("<b>1. INGESTION</b><br/><font size=6 color='#64748B'>M2M Scales &amp; GPS</font>", ParagraphStyle("P1", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
            Paragraph("<b>2. CROSS-CHECK</b><br/><font size=6 color='#64748B'>Permit &amp; Geofences</font>", ParagraphStyle("P2", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
            Paragraph("<b>3. RULE TRIGGER</b><br/><font size=6 color='#64748B'>11 Statutory Rules</font>", ParagraphStyle("P3", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
            Paragraph("<b>4. RISK SCORE</b><br/><font size=6 color='#64748B'>0–100 Scale</font>", ParagraphStyle("P4", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
            Paragraph("<b>5. SQUAD ALERT</b><br/><font size=6 color='#64748B'>Triage Console</font>", ParagraphStyle("P5", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
            Paragraph("<b>6. VERIFICATION</b><br/><font size=6 color='#64748B'>Roadside QR Scan</font>", ParagraphStyle("P6", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
            Paragraph("<b>7. DOSSIER</b><br/><font size=6 color='#64748B'>Evidence PDF</font>", ParagraphStyle("P7", alignment=1, fontName="Helvetica-Bold", fontSize=7)),
        ]
    ]
    t_pipe = Table(pipe_data, colWidths=[74, 74, 74, 74, 74, 74, 74])
    t_pipe.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('BOX', (0, 0), (-1, -1), 0.6, c_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(t_pipe)
    story.append(Spacer(1, 5))

    story.append(Paragraph("<b>The 11 Deterministic Statutory Detection Rules:</b>", h2_style))

    # Comprehensive Compact Table of 11 Rules
    rules_table_data = [
        [
            Paragraph("<b>Statutory Rule Name</b>", tbl_header),
            Paragraph("<b>Concrete Detection Trigger</b>", tbl_header),
            Paragraph("<b>Risk &amp; Severity</b>", tbl_header),
            Paragraph("<b>Statutory Objective</b>", tbl_header)
        ],
        [
            Paragraph("<b>1. Weight Anomaly (Overload)</b>", tbl_cell_bold),
            Paragraph("Actual Net Weight &gt; Permitted e-Rawaana Weight (or &gt; vehicle RTO gross limit).", tbl_cell),
            Paragraph("Medium to Critical (+30)", tbl_cell_alert),
            Paragraph("Prevent highway axle damage and recover evaded tonnage royalty.", tbl_cell)
        ],
        [
            Paragraph("<b>2. Route Corridor Deviation</b>", tbl_cell_bold),
            Paragraph("Perpendicular cross-track distance &gt; 500m from authorized polyline axis.", tbl_cell),
            Paragraph("Medium to Critical (+20)", tbl_cell_alert),
            Paragraph("Detect unpermitted diversion toward private crushers or riverbeds.", tbl_cell)
        ],
        [
            Paragraph("<b>3. GPS Signal Blackout</b>", tbl_cell_bold),
            Paragraph("No periodic AIS-140 telemetry pings received for &gt; 15 consecutive minutes.", tbl_cell),
            Paragraph("Medium to High (+20)", tbl_cell),
            Paragraph("Flag telematic loss; escalate if occurring near sensitive geofences.", tbl_cell)
        ],
        [
            Paragraph("<b>4. Permit Recycling / Reuse</b>", tbl_cell_bold),
            Paragraph("Attempted second haul on pass with status marked CONSUMED or EXPIRED.", tbl_cell),
            Paragraph("Critical (+30)", tbl_cell_alert),
            Paragraph("Eliminate 'Parchi reuse' fraud where single passes cover multiple trips.", tbl_cell)
        ],
        [
            Paragraph("<b>5. Vehicle-Permit Mismatch</b>", tbl_cell_bold),
            Paragraph("Physical vehicle registration does not match truck ID bound to transit pass.", tbl_cell),
            Paragraph("Critical (+30)", tbl_cell_alert),
            Paragraph("Prevent transfer of permits across unauthorized commercial tippers.", tbl_cell)
        ],
        [
            Paragraph("<b>6. Unauthorized Mine Entry</b>", tbl_cell_bold),
            Paragraph("Truck crosses quarry perimeter geofence without a valid active e-Rawaana.", tbl_cell),
            Paragraph("Critical (+30)", tbl_cell_alert),
            Paragraph("Detect unpermitted pithead access and illicit night loading operations.", tbl_cell)
        ],
        [
            Paragraph("<b>7. Impossible Speed / Transit</b>", tbl_cell_bold),
            Paragraph("Calculated transit speed &gt; 85 km/h commercial tipper legal limit.", tbl_cell),
            Paragraph("High to Critical (+30)", tbl_cell_alert),
            Paragraph("Expose fake paper-only 'ghost trips' or corrupted GPS telematics.", tbl_cell)
        ],
        [
            Paragraph("<b>8. Production Quota Mismatch</b>", tbl_cell_bold),
            Paragraph("Cumulative dispatch &gt; annual quota OR pithead mass balance variance &gt; 50 MT.", tbl_cell),
            Paragraph("High to Critical (+30)", tbl_cell_alert),
            Paragraph("Enforce environmental extraction caps; engage Tender Quota Kill-Switch.", tbl_cell)
        ],
        [
            Paragraph("<b>9. Manual Weight Override</b>", tbl_cell_bold),
            Paragraph("Scale gross or tare weight manually altered without automated transducer stream.", tbl_cell),
            Paragraph("Medium (+15)", tbl_cell),
            Paragraph("Audit scale operator interventions; mandate written supervisor reason.", tbl_cell)
        ],
        [
            Paragraph("<b>10. Tare Weight Inflation</b>", tbl_cell_bold),
            Paragraph("Recorded empty tare exceeds RTO Vahan baseline by &gt; 1.2 MT and &gt; 8.0%.", tbl_cell),
            Paragraph("High to Critical (+25)", tbl_cell_alert),
            Paragraph("Prevent concealed load fraud where heavy tare conceals mineral cargo.", tbl_cell)
        ],
        [
            Paragraph("<b>11. Inter-State Transit (ISTP)</b>", tbl_cell_bold),
            Paragraph("Interstate carrier crosses state border (e.g. Bawal Toll) without valid ISTP pass.", tbl_cell),
            Paragraph("Critical (+35)", tbl_cell_alert),
            Paragraph("Intercept unpermitted cross-border mineral smuggling into Haryana.", tbl_cell)
        ]
    ]
    t_rules = Table(rules_table_data, colWidths=[118, 165, 85, 150])
    t_rules.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 2.2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(t_rules)
    story.append(Spacer(1, 4))

    story.append(make_callout(
        "The risk score is capped at 100 points and categorized into transparent bands: "
        "<b>LOW (0–30)</b>, <b>MEDIUM (31–60)</b>, <b>HIGH (61–80)</b>, and <b>CRITICAL (81–100)</b>. "
        "Enforcement officers receive an itemized breakdown showing exactly which rules were triggered and why.",
        title="TRANSPARENT RISK BANDS",
        border_col="#0F3826", bg_col="#F0FDF4", text_col="#166534"
    ))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 6: REAL EXAMPLE (HR26AB1234)
    # =========================================================================
    story.append(Paragraph("5. ILLUSTRATIVE TRIP AUDIT: ONE TRUCK, COMPLETE TIMELINE", h1_style))
    story.append(make_divider())

    story.append(Paragraph(
        "To understand how SmartMineGuard works in practice, review the following documented demonstration scenario. "
        "It illustrates how an individual commercial tipper journey is captured as an integrated chronological audit trail.",
        body_style
    ))
    story.append(Spacer(1, 2))

    story.append(make_callout(
        "This scenario is an <b>illustrative prototype demonstration</b> using simulated data to demonstrate system capabilities. "
        "It does not represent an actual enforcement action or real private commercial records.",
        title="PROTOTYPE DEMONSTRATION SCENARIO",
        border_col="#475569", bg_col="#F8FAFC", text_col="#334155"
    ))
    story.append(Spacer(1, 3))

    # Vehicle & Permit Parameters Profile Table
    param_data = [
        [
            Paragraph("<b>Target Vehicle Number:</b>", tbl_cell_bold),
            Paragraph("HR26AB1234 (10-Wheeler Tipper)", tbl_cell),
            Paragraph("<b>e-Rawaana Permit No.:</b>", tbl_cell_bold),
            Paragraph("SMG-2026-00125", tbl_cell)
        ],
        [
            Paragraph("<b>Mineral Classification:</b>", tbl_cell_bold),
            Paragraph("Quartzite Aggregate (Khanak)", tbl_cell),
            Paragraph("<b>Permitted Transit Weight:</b>", tbl_cell_bold),
            Paragraph("24.00 Metric Tonnes (MT)", tbl_cell_bold)
        ],
        [
            Paragraph("<b>Scale Gross Weight:</b>", tbl_cell_bold),
            Paragraph("35.80 Metric Tonnes (MT)", tbl_cell),
            Paragraph("<b>Scale Tare Weight:</b>", tbl_cell_bold),
            Paragraph("11.20 Metric Tonnes (MT)", tbl_cell)
        ],
        [
            Paragraph("<b>Calculated Net Payload:</b>", tbl_cell_bold),
            Paragraph("<b>24.60 Metric Tonnes (MT)</b>", tbl_cell_bold),
            Paragraph("<b>Net Variance / Excess:</b>", tbl_cell_bold),
            Paragraph("<font color='#991B1B'><b>+0.60 MT Overload (+2.5%)</b></font>", tbl_cell_alert)
        ]
    ]
    t_param = Table(param_data, colWidths=[120, 140, 120, 138])
    t_param.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor("#F1F5F9")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_param)
    story.append(Spacer(1, 4))

    story.append(Paragraph("<b>Complete Chronological Trip Milestone Ledger:</b>", h2_style))

    # Chronological Journey Timeline Table
    timeline_rows = [
        [
            Paragraph("<b>Time</b>", tbl_header),
            Paragraph("<b>Milestone Event</b>", tbl_header),
            Paragraph("<b>System Action &amp; Statutory Audit Finding</b>", tbl_header),
            Paragraph("<b>Status / Risk</b>", tbl_header)
        ],
        [
            Paragraph("08:12", tbl_cell_bold),
            Paragraph("Mine Geofence Entry", tbl_cell_bold),
            Paragraph("Truck crosses quarry perimeter. GPS triggers automated arrival; searches active permit registry.", tbl_cell),
            Paragraph("NORMAL (0)", tbl_cell)
        ],
        [
            Paragraph("08:15", tbl_cell_bold),
            Paragraph("Permit Matched", tbl_cell_bold),
            Paragraph("Valid e-Rawaana SMG-2026-00125 auto-matched. Quota checked; shift round counter initialized.", tbl_cell),
            Paragraph("VALID (0)", tbl_cell)
        ],
        [
            Paragraph("08:22", tbl_cell_bold),
            Paragraph("Pit Loading Started", tbl_cell_bold),
            Paragraph("Truck positions at quarry extraction hopper. Trip status transitions to LOADING.", tbl_cell),
            Paragraph("NORMAL (0)", tbl_cell)
        ],
        [
            Paragraph("08:28", tbl_cell_bold),
            Paragraph("Scale Weighment", tbl_cell_bold),
            Paragraph("Pithead scale captures Gross (35.8 MT) and Tare (11.2 MT). Platform IR interlock confirms deck alignment.", tbl_cell),
            Paragraph("WEIGHED", tbl_cell)
        ],
        [
            Paragraph("08:29", tbl_cell_bold),
            Paragraph("Net Payload Audit", tbl_cell_bold),
            Paragraph("Deterministic calculation: Net = 24.6 MT vs. Permitted = 24.0 MT. Excess +0.6 MT logged in ledger.", tbl_cell),
            Paragraph("OVERWEIGHT (+30)", tbl_cell_alert)
        ],
        [
            Paragraph("08:34", tbl_cell_bold),
            Paragraph("Dispatch Cleared", tbl_cell_bold),
            Paragraph("Outbound transit pass generated. Weighment manifest sealed cryptographically.", tbl_cell),
            Paragraph("DISPATCHED", tbl_cell)
        ],
        [
            Paragraph("08:42", tbl_cell_bold),
            Paragraph("Mine Geofence Exit", tbl_cell_bold),
            Paragraph("Vehicle exits mine perimeter geofence. System starts transit timer; increments driver round tally.", tbl_cell),
            Paragraph("IN_TRANSIT", tbl_cell)
        ],
        [
            Paragraph("09:25", tbl_cell_bold),
            Paragraph("GPS Blackout Event", tbl_cell_bold),
            Paragraph("AIS-140 telemetry pings cease along transit corridor. 15-minute timer triggers alert to squad console.", tbl_cell),
            Paragraph("BLACKOUT (+20)", tbl_cell_alert)
        ],
        [
            Paragraph("10:05", tbl_cell_bold),
            Paragraph("Signal Restored", tbl_cell_bold),
            Paragraph("Telemetry resumes near highway junction. 40-minute blackout window archived as investigative evidence.", tbl_cell),
            Paragraph("FLAGGED (50)", tbl_cell_alert)
        ]
    ]
    t_timeline = Table(timeline_rows, colWidths=[42, 105, 275, 96])
    t_timeline.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 2.3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(t_timeline)
    story.append(Spacer(1, 4))

    story.append(Paragraph(
        "<b>Why Chronological Timelines Matter to Enforcement Officers:</b><br/>"
        "In traditional enforcement, an officer intercepting truck HR26AB1234 at 10:30 AM would see only a printed paper permit "
        "and have no way to know that the truck experienced a 40-minute telemetry blackout or was dispatched with an unbilled +0.6 MT overload. "
        "SmartMineGuard gives the officer the <b>entire unbroken lifecycle</b> at a glance.",
        body_style
    ))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 7: OFFICER WORKFLOW + EVIDENCE
    # =========================================================================
    story.append(Paragraph("6. FROM ALERT TO OFFICER FIELD VERIFICATION", h1_style))
    story.append(make_divider())

    story.append(Paragraph(
        "SmartMineGuard is engineered as an officer decision-support platform. The software automates surveillance, "
        "data correlation, and evidence compilation—empowering field squads to conduct rapid, legally sound verifications.",
        body_style
    ))
    story.append(Spacer(1, 2.5))

    # 10-Step Workflow Table
    story.append(Paragraph("<b>The 10-Step Operational Enforcement Workflow:</b>", h2_style))
    
    workflow_steps = [
        [
            Paragraph("<b>Stage</b>", tbl_header),
            Paragraph("<b>Officer Action &amp; System Interaction</b>", tbl_header),
            Paragraph("<b>Operational Outcome</b>", tbl_header)
        ],
        [
            Paragraph("Step 1", tbl_cell_bold),
            Paragraph("Alert Surfaces in Console: An alert appears in the Enforcement Squad queue ranked by severity.", tbl_cell),
            Paragraph("Squad prioritizes target vehicle based on risk score.", tbl_cell)
        ],
        [
            Paragraph("Step 2", tbl_cell_bold),
            Paragraph("Select Vehicle: Officer selects vehicle (e.g. HR26AB1234) to open the real-time inspector.", tbl_cell),
            Paragraph("Displays active permit, driver, and current coordinates.", tbl_cell)
        ],
        [
            Paragraph("Step 3", tbl_cell_bold),
            Paragraph("Review Flagged Reason: Officer inspects exact statutory rule triggered and numerical variance.", tbl_cell),
            Paragraph("No ambiguous predictions; concrete violation data.", tbl_cell)
        ],
        [
            Paragraph("Step 4", tbl_cell_bold),
            Paragraph("Live GIS Tracking: Officer views vehicle on Leaflet GIS map with route corridor buffers.", tbl_cell),
            Paragraph("Tracks vehicle trajectory toward checkpoint intercept.", tbl_cell)
        ],
        [
            Paragraph("Step 5", tbl_cell_bold),
            Paragraph("Inspect Timeline: Officer reviews the chronological event ledger from pithead to transit.", tbl_cell),
            Paragraph("Identifies blackout duration or corridor departure point.", tbl_cell)
        ],
        [
            Paragraph("Step 6", tbl_cell_bold),
            Paragraph("Roadside QR Scan: Intercepting squad scans vehicle's digital/paper QR code via mobile camera.", tbl_cell),
            Paragraph("Instant verification: Confirms valid, expired, or recycled pass.", tbl_cell)
        ],
        [
            Paragraph("Step 7", tbl_cell_bold),
            Paragraph("Review Weighment: Officer examines certified scale gross, tare, and net weighment receipt.", tbl_cell),
            Paragraph("Confirms whether weight exceeds registered gross capacity.", tbl_cell)
        ],
        [
            Paragraph("Step 8", tbl_cell_bold),
            Paragraph("Examine Telematics: Officer reviews spatial deviation distance (meters) or blackout log.", tbl_cell),
            Paragraph("Corroborates driver explanation against GPS data.", tbl_cell)
        ],
        [
            Paragraph("Step 9", tbl_cell_bold),
            Paragraph("Record Field Findings: Officer enters on-site physical inspection notes into mobile portal.", tbl_cell),
            Paragraph("Immutable audit trail created under officer badge ID.", tbl_cell)
        ],
        [
            Paragraph("Step 10", tbl_cell_bold),
            Paragraph("Generate Evidence Dossier: System compiles structured case record into an official PDF dossier.", tbl_cell),
            Paragraph("Official documentation ready for statutory compounding.", tbl_cell)
        ]
    ]
    t_workflow = Table(workflow_steps, colWidths=[42, 336, 140])
    t_workflow.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 1.8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(t_workflow)
    story.append(Spacer(1, 4))

    story.append(Paragraph("<b>Contents of the Statutory Evidence Dossier PDF:</b>", h2_style))
    story.append(Paragraph(
        "When an officer elevates an alert to a formal investigation file, SmartMineGuard compiles an official dossier containing:<br/>"
        "• <b>Vehicle &amp; Owner Profile:</b> Registration number, chassis classification, registered transporter, and RTO tare baseline.<br/>"
        "• <b>e-Rawaana Permit Metadata:</b> Pass number, QR security hash, sanctioned tonnage, mineral grade, and destination.<br/>"
        "• <b>Certified Scale Receipts:</b> Gross, tare, and net weights with automated scale ID and manual override audit history.<br/>"
        "• <b>Chronological Milestone Log:</b> Exact timestamps of mine entry, loading, scale capture, gate exit, and checkpoints.<br/>"
        "• <b>Spatial Deviation Evidence:</b> Measured perpendicular departure distance (meters) and GPS telemetry blackout timestamps.<br/>"
        "• <b>Officer Notes &amp; Findings:</b> Field inspection observations, compounding fee calculations, and official signature blocks.",
        bullet_style
    ))
    story.append(Spacer(1, 3))

    legal_notice = make_callout(
        "<b>\"The Evidence Dossier is designed to support official administrative investigation and statutory documentation. "
        "It does not replace statutory administrative procedures or judicial discretion under Section 21 of the MMDR Act.\"</b><br/>"
        "All compounding orders, vehicle seizures, and formal penal notices remain subject to the physical inspection, "
        "substantive findings, and final determination of the authorized mining officer.",
        title="STATUTORY & LEGAL INTEGRITY NOTICE",
        border_col="#0F3826", bg_col="#ECFDF5", text_col="#065F46"
    )
    story.append(legal_notice)

    story.append(PageBreak())

    # =========================================================================
    # PAGE 8: PROTOTYPE BOUNDARIES + NEXT STEPS
    # =========================================================================
    story.append(Paragraph("7. PROTOTYPE SCOPE &amp; DEPLOYMENT PATH", h1_style))
    story.append(make_divider())

    story.append(Paragraph(
        "In the spirit of technical transparency and academic rigor, the current operational boundaries of the "
        "SmartMineGuard demonstration prototype are explicitly documented below:",
        body_style
    ))
    story.append(Spacer(1, 2.5))

    # Prototype Boundaries Table
    bounds_data = [
        [
            Paragraph("<b>System Dimension</b>", tbl_header),
            Paragraph("<b>Current Demonstration Prototype State</b>", tbl_header),
            Paragraph("<b>Production Deployment Requirement</b>", tbl_header)
        ],
        [
            Paragraph("GPS Vehicle Tracking", tbl_cell_bold),
            Paragraph("Simulated multi-truck telematic movement across realistic Haryana mining corridors.", tbl_cell),
            Paragraph("Direct server webhook / MQTT ingestion from physical AIS-140 GPS transponder vendors.", tbl_cell)
        ],
        [
            Paragraph("Weighbridge Scale Feeds", tbl_cell_bold),
            Paragraph("Structured synthetic weighment datasets representing real-world Gross/Tare values.", tbl_cell),
            Paragraph("Standard RS-232 / WebSerial / IoT digital indicator bridges on physical scale decks.", tbl_cell)
        ],
        [
            Paragraph("National Portals (VAHAN)", tbl_cell_bold),
            Paragraph("Simulated RTO unladen tare baselines and vehicle ownership registries in local DB.", tbl_cell),
            Paragraph("Secure API integration with National Transport Project (VAHAN/SARATHI) gateways.", tbl_cell)
        ],
        [
            Paragraph("State e-Rawaana Integration", tbl_cell_bold),
            Paragraph("Embedded statutory permit generation and QR verification mimicking state rules.", tbl_cell),
            Paragraph("Bi-directional REST API integration with State Department e-Rawaana production server.", tbl_cell)
        ]
    ]
    t_bounds = Table(bounds_data, colWidths=[110, 204, 204])
    t_bounds.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(t_bounds)
    story.append(Spacer(1, 4))

    story.append(Paragraph("<b>The Six-Stage Roadmap to Operational Deployment:</b>", h2_style))

    # Deployment Ladder Diagram (clean horizontal/vertical steps without unicode)
    ladder_data = [
        [Paragraph("<b>STAGE 1: Functional Prototype &amp; Academic Validation</b> (Current Status: Fully Operational Demonstration)", ParagraphStyle("S1", fontSize=7.5, fontName="Helvetica-Bold", textColor=c_primary))],
        [Paragraph("|", ParagraphStyle("Arr", alignment=1, fontSize=8, textColor=c_primary))],
        [Paragraph("<b>STAGE 2: Technical &amp; Statutory Validation</b> with Mining Department &amp; Enforcement Squad Officials", ParagraphStyle("S2", fontSize=7.5, fontName="Helvetica", textColor=c_dark))],
        [Paragraph("|", ParagraphStyle("Arr", alignment=1, fontSize=8, textColor=c_primary))],
        [Paragraph("<b>STAGE 3: Field Squad &amp; Domain Expert Feedback</b> to Refine Regional Thresholds &amp; Geofence Coordinates", ParagraphStyle("S3", fontSize=7.5, fontName="Helvetica", textColor=c_dark))],
        [Paragraph("|", ParagraphStyle("Arr", alignment=1, fontSize=8, textColor=c_primary))],
        [Paragraph("<b>STAGE 4: Controlled Pilot Deployment</b> on a Single Selected Quarry Corridor / Weighbridge Cluster (e.g. Khanak)", ParagraphStyle("S4", fontSize=7.5, fontName="Helvetica", textColor=c_dark))],
        [Paragraph("|", ParagraphStyle("Arr", alignment=1, fontSize=8, textColor=c_primary))],
        [Paragraph("<b>STAGE 5: Live API Integration</b> with AIS-140 Telematic Gateways &amp; Certified Weighbridge Scale Transducers", ParagraphStyle("S5", fontSize=7.5, fontName="Helvetica", textColor=c_dark))],
        [Paragraph("|", ParagraphStyle("Arr", alignment=1, fontSize=8, textColor=c_primary))],
        [Paragraph("<b>STAGE 6: Statewide Operational Deployment</b> &amp; Ongoing Statutory Surveillance Rollout", ParagraphStyle("S6", fontSize=7.5, fontName="Helvetica-Bold", textColor=c_primary))]
    ]
    t_ladder = Table(ladder_data, colWidths=[518])
    t_ladder.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('BOX', (0, 0), (-1, -1), 0.6, c_border),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 1.2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.2),
    ]))
    story.append(t_ladder)
    story.append(Spacer(1, 4))

    story.append(make_callout(
        "\"SmartMineGuard is respectfully presented for technical and operational feedback, domain evaluation, "
        "and statutory guidance from competent Mining &amp; Enforcement Authorities.\"",
        title="INVITATION FOR TECHNICAL EVALUATION",
        border_col="#0F3826", bg_col="#ECFDF5", text_col="#065F46"
    ))
    story.append(Spacer(1, 4))

    # Project Information & Contact Block
    contact_data = [
        [
            Paragraph("<b>Project Title:</b>", tbl_cell_bold),
            Paragraph("SmartMineGuard", tbl_cell),
            Paragraph("<b>Target Sector:</b>", tbl_cell_bold),
            Paragraph("Mineral Transit &amp; Concession Surveillance", tbl_cell)
        ],
        [
            Paragraph("<b>Core Repository:</b>", tbl_cell_bold),
            Paragraph("https://github.com/jaipalverma808/smartmineguard", tbl_cell),
            Paragraph("<b>Demonstration:</b>", tbl_cell_bold),
            Paragraph("Standalone Software Prototype (Flask/PostGIS)", tbl_cell)
        ],
        [
            Paragraph("<b>Development Team:</b>", tbl_cell_bold),
            Paragraph("SmartMineGuard Student Development Team (Team Codeavengerz)", tbl_cell),
            Paragraph("<b>Submission Track:</b>", tbl_cell_bold),
            Paragraph("Smart India Hackathon (SIH) 2026", tbl_cell)
        ]
    ]
    t_contact = Table(contact_data, colWidths=[105, 185, 95, 133])
    t_contact.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor("#F1F5F9")),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]))
    story.append(t_contact)

    doc.build(story, canvasmaker=ConceptNoteCanvas)
    print(f"[SUCCESS] Concept Note PDF compiled at: {OUTPUT_PDF}")

    # Copy to workspace root
    try:
        import shutil
        shutil.copy2(OUTPUT_PDF, WORKSPACE_PDF)
        print(f"[SUCCESS] Copied Concept Note to workspace: {WORKSPACE_PDF}")
    except Exception as e:
        print(f"[WARNING] Workspace copy error: {e}")


if __name__ == "__main__":
    build_concept_note_pdf()
