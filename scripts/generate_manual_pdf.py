"""
SmartMineGuard User Manual PDF Generator
Generates a comprehensive, screenshot-based, user-facing feature & function manual
in PDF format using ReportLab.
STRICTLY NON-TECHNICAL — PURE USER FUNCTIONALITY, PURPOSE, DATA, AND WORKFLOWS.
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
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage, KeepTogether, PageBreak
)
from reportlab.pdfgen import canvas
from PIL import Image as PILImage

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "static" / "manual_assets"
OUTPUT_PDF = BASE_DIR / "SmartMineGuard_Complete_User_Feature_Manual.pdf"


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and print 'Page X of Y' 
    and formal running administrative headers.
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
            return  # Skip cover page
        self.saveState()
        
        # Running Top Header
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#0F3826"))
        self.drawString(36, 812, "SMARTMINEGUARD")
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#475569"))
        self.drawString(130, 812, "— Comprehensive User-Facing Feature & Function Manual")
        self.drawRightString(559, 812, "MINERAL TRANSIT INTELLIGENCE PLATFORM")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.6)
        self.line(36, 806, 559, 806)

        # Running Bottom Footer
        self.line(36, 44, 559, 44)
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor("#0F3826"))
        self.drawString(36, 32, "STATUTORY SURVEILLANCE & RECONCILIATION MANUAL")
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(275, 32, "Pure Software Architecture • Deterministic Rule Governance")
        self.drawRightString(559, 32, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def get_image_flowable(filename, target_width=490, max_height=320):
    img_path = ASSETS_DIR / filename
    if not img_path.exists():
        return Paragraph(f"<i>[Screenshot placeholder: {filename}]</i>", getSampleStyleSheet()["Normal"])
    try:
        with PILImage.open(img_path) as im:
            w, h = im.size
            aspect = h / float(w)
            tw = target_width
            th = tw * aspect
            if th > max_height:
                th = max_height
                tw = th / aspect
            return RLImage(str(img_path), width=tw, height=th)
    except Exception as e:
        return Paragraph(f"<i>[Error rendering screenshot: {e}]</i>", getSampleStyleSheet()["Normal"])


def build_manual_pdf():
    print("[*] Compiling SmartMineGuard Complete User Feature Manual PDF...")
    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=46,
        bottomMargin=52
    )

    styles = getSampleStyleSheet()

    # Custom Styles
    c_primary = colors.HexColor("#0F3826")      # Forest Green
    c_secondary = colors.HexColor("#D97706")    # Amber / Gold
    c_dark = colors.HexColor("#0F172A")         # Slate Dark
    c_card_bg = colors.HexColor("#F8FAFC")      # Slate 50
    c_crimson = colors.HexColor("#991B1B")      # Alert Red

    title_style = ParagraphStyle(
        "CoverTitle",
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=30,
        textColor=colors.white,
        alignment=1
    )

    subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        fontName="Helvetica",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#E2E8F0"),
        alignment=1
    )

    h1_style = ParagraphStyle(
        "Heading1_Custom",
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=c_primary,
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        "Heading2_Custom",
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=c_dark,
        spaceBefore=9,
        spaceAfter=4,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        "Body_Custom",
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=3,
        spaceAfter=3
    )

    bullet_style = ParagraphStyle(
        "Bullet_Custom",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#334155"),
        leftIndent=12,
        spaceBefore=2,
        spaceAfter=2
    )

    callout_text = ParagraphStyle(
        "CalloutText",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#0F3826")
    )

    badge_text = ParagraphStyle(
        "BadgeText",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1
    )

    caption_style = ParagraphStyle(
        "CaptionStyle",
        fontName="Helvetica-Oblique",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#64748B"),
        alignment=1,
        spaceBefore=3,
        spaceAfter=6
    )

    tbl_header = ParagraphStyle(
        "TblHeader",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
        alignment=0
    )

    tbl_cell = ParagraphStyle(
        "TblCell",
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1E293B")
    )

    tbl_cell_bold = ParagraphStyle(
        "TblCellBold",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#0F172A")
    )

    def make_callout(text, title="IMPORTANT NOTICE", border_color="#0F3826", bg_color="#ECFDF5", text_color="#065F46"):
        title_p = Paragraph(f"<b>{title}:</b> {text}", ParagraphStyle(
            "CInner", fontName="Helvetica", fontSize=8.5, leading=12, textColor=colors.HexColor(text_color)
        ))
        t = Table([[title_p]], colWidths=[510])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(bg_color)),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor(border_color)),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        return t

    def make_section_divider():
        return HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E1"), spaceBefore=10, spaceAfter=10)

    story = []

    # =========================================================================
    # COVER PAGE
    # =========================================================================
    story.append(Spacer(1, 40))
    cover_data = [
        [Paragraph("<font size=11 color='#D4AF37'><b>STATE DIRECTORATE OF MINES & GEOLOGY</b></font><br/><br/>", ParagraphStyle("CoverTop", alignment=1))],
        [Paragraph("SMARTMINEGUARD", title_style)],
        [Spacer(1, 6)],
        [Paragraph("<b>COMPLETE USER-FACING FEATURE &amp; FUNCTION MANUAL</b><br/>"
                   "<font size=10 color='#A7F3D0'>Anti-Fraud Dispatch Control, Real-Time GIS Surveillance &amp; Automated Mine Trip Reconciliation</font>", subtitle_style)],
        [Spacer(1, 15)],
        [Paragraph("<font size=8.5 color='#CBD5E1'>OFFICIAL SYSTEM OPERATOR &amp; ENFORCEMENT GUIDE<br/>"
                   "Strictly User-Facing • Non-Technical Manual • Publication Edition 2026</font>", ParagraphStyle("CoverSub2", alignment=1))]
    ]
    cover_table = Table(cover_data, colWidths=[510])
    cover_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_primary),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 24),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 24),
        ('LEFTPADDING', (0, 0), (-1, -1), 16),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16),
        ('BOX', (0, 0), (-1, -1), 2, colors.HexColor("#D4AF37")),
    ]))
    story.append(cover_table)

    story.append(Spacer(1, 25))

    # Executive Overview Callout on Cover
    cover_summary = [
        [Paragraph("<b>ABOUT THIS USER MANUAL</b>", ParagraphStyle("CovBoxH", fontName="Helvetica-Bold", fontSize=10, textColor=c_primary))],
        [Paragraph("This comprehensive guide explains <b>every screen, button, metric, alert, table, and workflow</b> "
                   "present within the live SmartMineGuard application. It is written exclusively from an operational "
                   "and administrative perspective. <b>No code, no programming logic, and no database syntax</b> are used. "
                   "Whether you are an <b>Administrator</b> overseeing state-wide dispatch quotas, an <b>Enforcement Officer</b> "
                   "monitoring route corridor compliance on the live GIS map, or a <b>Leasehold Operator</b> managing pithead loading, "
                   "this manual serves as your definitive operational playbook.", body_style)],
        [Spacer(1, 4)],
        [Paragraph("<b>Primary Architectural Pillars Explained:</b><br/>"
                   "• <b>GPS Mine Geofencing</b>: Authoritative automated mine entry and exit detection.<br/>"
                   "• <b>Smart e-Rawaana Reconciliation</b>: Real-time transit permit auto-matching and reuse prevention.<br/>"
                   "• <b>Automated Scale Weighment</b>: Pure net mineral payload math with manual override audit trails.<br/>"
                   "• <b>Truck Round Counter &amp; Quotas</b>: Tracking daily round limits and preventing permit generation for completed shifts.<br/>"
                   "• <b>Leaflet Route Reconstruction</b>: Visualizing authorized transport corridors vs. actual historical GPS breadcrumbs.<br/>"
                   "• <b>Mass-Balance Accounting</b>: Reconciling opening stock, daily production, and dispatched quantities.", bullet_style)]
    ]
    cov_summary_table = Table(cover_summary, colWidths=[510])
    cov_summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), c_card_bg),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 14),
        ('RIGHTPADDING', (0, 0), (-1, -1), 14),
    ]))
    story.append(cov_summary_table)

    story.append(Spacer(1, 20))

    # Document Metadata Block
    meta_data = [
        [Paragraph("<b>Document Identifier:</b>", tbl_cell_bold), Paragraph("SMG-MAN-2026-V2.5", tbl_cell),
         Paragraph("<b>Effective Date:</b>", tbl_cell_bold), Paragraph(datetime.now().strftime("%d %B %Y"), tbl_cell)],
        [Paragraph("<b>Target Audience:</b>", tbl_cell_bold), Paragraph("State Mining Directors, Enforcement Officers, Lease Operators", tbl_cell),
         Paragraph("<b>Jurisdiction:</b>", tbl_cell_bold), Paragraph("Indian Mineral Concession & Transport Rules", tbl_cell)],
        [Paragraph("<b>Platform Scope:</b>", tbl_cell_bold), Paragraph("Pure Software Platform (Deterministic Rule Engine)", tbl_cell),
         Paragraph("<b>Security Notice:</b>", tbl_cell_bold), Paragraph("Zero Sensitive Credentials Exposed", tbl_cell)],
    ]
    meta_table = Table(meta_data, colWidths=[110, 160, 100, 140])
    meta_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor("#F1F5F9")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)

    story.append(PageBreak())

    # =========================================================================
    # TABLE OF CONTENTS
    # =========================================================================
    story.append(Paragraph("TABLE OF CONTENTS", h1_style))
    story.append(make_section_divider())

    toc_data = [
        [Paragraph("<b>Chapter / Section</b>", tbl_header), Paragraph("<b>Core Subject Matter &amp; User Workflows</b>", tbl_header), Paragraph("<b>Target User</b>", tbl_header)],
        [Paragraph("<b>1. What is SmartMineGuard?</b>", tbl_cell_bold), Paragraph("Problem statement, why GPS & e-Rawaana matter, full high-level dispatch lifecycle.", tbl_cell), Paragraph("All Users", tbl_cell)],
        [Paragraph("<b>2. Conceptual Data Flow (No Code)</b>", tbl_cell_bold), Paragraph("How Mines, Trucks, Drivers, Permits, Trips, and Weighbridges interconnect.", tbl_cell), Paragraph("All Users", tbl_cell)],
        [Paragraph("<b>3. Security, Privacy &amp; Boundaries</b>", tbl_cell_bold), Paragraph("Why sensitive surveillance is sealed from public and credentials kept safe.", tbl_cell), Paragraph("All Users", tbl_cell)],
        [Paragraph("<b>4. Public Information Portal ( / )</b>", tbl_cell_bold), Paragraph("Safe district lookup, public verification of e-Rawaana, vehicle, and ISTP numbers.", tbl_cell), Paragraph("Public / Transporters", tbl_cell)],
        [Paragraph("<b>5. Login &amp; Role Authentication</b>", tbl_cell_bold), Paragraph("Accessing secure consoles, user sessions, role-based entry disclaimers.", tbl_cell), Paragraph("Admin, Officer, Operator", tbl_cell)],
        [Paragraph("<b>6. Role-Based Access Control (RBAC)</b>", tbl_cell_bold), Paragraph("System governance matrix comparing Admin, Officer, and Operator privileges.", tbl_cell), Paragraph("All Users", tbl_cell)],
        [Paragraph("<b>7. Admin Command Center</b>", tbl_cell_bold), Paragraph("State-wide surveillance, dispatch control, stock balances, production mismatch alerts.", tbl_cell), Paragraph("Administrator", tbl_cell)],
        [Paragraph("<b>8. Operator Dashboard</b>", tbl_cell_bold), Paragraph("Daily pithead queue, opening stock, daily production, dispatch planning balance.", tbl_cell), Paragraph("Lease Operator", tbl_cell)],
        [Paragraph("<b>9. Officer Enforcement Command Center</b>", tbl_cell_bold), Paragraph("High-risk truck interception queue, critical alerts triage, roadside actions.", tbl_cell), Paragraph("Enforcement Officer", tbl_cell)],
        [Paragraph("<b>10. Live GIS Map &amp; Navigation</b>", tbl_cell_bold), Paragraph("Interactive map canvas, vehicle markers, geofences, corridors, fleet drawer.", tbl_cell), Paragraph("Officer, Admin", tbl_cell)],
        [Paragraph("<b>11. Route Reconstruction &amp; Deviation</b>", tbl_cell_bold), Paragraph("Authorized corridor vs. actual historical GPS breadcrumbs, illegal diversion flags.", tbl_cell), Paragraph("Officer, Admin", tbl_cell)],
        [Paragraph("<b>12. Chronological Trip Audit Timeline</b>", tbl_cell_bold), Paragraph("Real-time milestone ledger: mine entry, scale weight, dispatch clearance, blackout.", tbl_cell), Paragraph("Officer, Admin, Operator", tbl_cell)],
        [Paragraph("<b>13. Truck Fleet Management &amp; Detail</b>", tbl_cell_bold), Paragraph("Vehicle registry, geofence round quotas, multi-period cumulative tonnage cards.", tbl_cell), Paragraph("All Users", tbl_cell)],
        [Paragraph("<b>14. e-Rawaana Transit Permits</b>", tbl_cell_bold), Paragraph("Statutory pass verification, validity windows, cryptographic QR code inspection.", tbl_cell), Paragraph("All Users", tbl_cell)],
        [Paragraph("<b>15. Transit Trips Ledger</b>", tbl_cell_bold), Paragraph("Monitoring transit duration, speeds, destination compliance, round numbering.", tbl_cell), Paragraph("Officer, Admin, Operator", tbl_cell)],
        [Paragraph("<b>16. Automated Weighbridge Integration</b>", tbl_cell_bold), Paragraph("Automated net weight calculation (Gross - Tare), overload rules, manual override audit.", tbl_cell), Paragraph("Operator, Officer, Admin", tbl_cell)],
        [Paragraph("<b>17. Pithead Stock Mass-Balance</b>", tbl_cell_bold), Paragraph("Stock accounting formula, physical vs. expected discrepancies, statutory tolerance.", tbl_cell), Paragraph("Admin, Operator", tbl_cell)],
        [Paragraph("<b>18. Truck Round Counter &amp; Quotas</b>", tbl_cell_bold), Paragraph("Geofenced round cycles, excessive trip frequency detection, permit blocking.", tbl_cell), Paragraph("All Users", tbl_cell)],
        [Paragraph("<b>19. Deterministic Detection Engine</b>", tbl_cell_bold), Paragraph("User perspective on all 11 statutory rules (Overload, Blackout, Deviation, etc.).", tbl_cell), Paragraph("Officer, Admin", tbl_cell)],
        [Paragraph("<b>20. Explainable Risk Scoring (0–100)</b>", tbl_cell_bold), Paragraph("Transparent risk point additions (+30 Overweight, +20 Deviation), zero AI claims.", tbl_cell), Paragraph("Officer, Admin", tbl_cell)],
        [Paragraph("<b>21. Alerts Center &amp; Triage</b>", tbl_cell_bold), Paragraph("Severity tiers, alert lifecycle states (New, Acknowledged, Investigating, Resolved).", tbl_cell), Paragraph("Officer, Admin", tbl_cell)],
        [Paragraph("<b>22. Investigations &amp; Case Files</b>", tbl_cell_bold), Paragraph("Opening cases, attaching evidence, logging officer findings, penalty decisions.", tbl_cell), Paragraph("Enforcement Officer", tbl_cell)],
        [Paragraph("<b>23. Officer Roadside QR Verification</b>", tbl_cell_bold), Paragraph("Mobile-friendly verification module, QR scanner, roadside pass authenticity.", tbl_cell), Paragraph("Enforcement Officer", tbl_cell)],
        [Paragraph("<b>24. Reports &amp; Evidence Dossiers</b>", tbl_cell_bold), Paragraph("Official statutory evidence dossiers, printable investigation certificates.", tbl_cell), Paragraph("Officer, Admin", tbl_cell)],
        [Paragraph("<b>25. Analytics Dashboard</b>", tbl_cell_bold), Paragraph("State-wide volume trends, risk distribution, corridor compliance charts.", tbl_cell), Paragraph("Admin, Officer", tbl_cell)],
        [Paragraph("<b>26. Master Data Management Console</b>", tbl_cell_bold), Paragraph("Managing Mines, Trucks, Drivers, Passes, Weighbridges, Destinations, Checkpoints.", tbl_cell), Paragraph("Admin, Operator", tbl_cell)],
        [Paragraph("<b>27. Quota Guardrail for Completed Rounds</b>", tbl_cell_bold), Paragraph("Permit modal validation strictly blocking pass generation for exhausted round quotas.", tbl_cell), Paragraph("Admin, Operator", tbl_cell)],
        [Paragraph("<b>28. User &amp; Badge Management</b>", tbl_cell_bold), Paragraph("Admin console for departmental badge numbers, roles, and credential management.", tbl_cell), Paragraph("Administrator", tbl_cell)],
        [Paragraph("<b>29. One Complete Truck Journey</b>", tbl_cell_bold), Paragraph("End-to-end operational walkthrough of truck HR26AB1234 from registration to dossier.", tbl_cell), Paragraph("All Users", tbl_cell)],
        [Paragraph("<b>30. Illegal / Suspicious Case Studies</b>", tbl_cell_bold), Paragraph("6 realistic violation scenarios (Overloading, Night Blackout, Diversion, Recycling).", tbl_cell), Paragraph("Officer, Admin", tbl_cell)],
        [Paragraph("<b>31. Daily Operational Playbooks</b>", tbl_cell_bold), Paragraph("Daily step-by-step checklists for Admin, Officer, and Operator roles.", tbl_cell), Paragraph("Admin, Officer, Operator", tbl_cell)],
        [Paragraph("<b>32. 'What Should I Check First?' Triage</b>", tbl_cell_bold), Paragraph("Immediate incident response guide for critical alerts and pithead dispatches.", tbl_cell), Paragraph("All Users", tbl_cell)],
        [Paragraph("<b>33. Demo &amp; Simulation Boundaries</b>", tbl_cell_bold), Paragraph("Transparent disclosure of synthetic GPS simulation vs. real hardware requirements.", tbl_cell), Paragraph("All Users / Evaluators", tbl_cell)],
        [Paragraph("<b>34. Master Quick-Reference Tables</b>", tbl_cell_bold), Paragraph("Screen Directory, Core Feature Matrix, RBAC Summary, and Lifecycle Diagram.", tbl_cell), Paragraph("All Users", tbl_cell)]
    ]

    toc_table = Table(toc_data, colWidths=[150, 270, 90])
    toc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(toc_table)

    story.append(PageBreak())

    # =========================================================================
    # SECTION 1: WHAT IS SMARTMINEGUARD?
    # =========================================================================
    story.append(Paragraph("SECTION 1 — WHAT IS SMARTMINEGUARD?", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "<b>SmartMineGuard</b> is a specialized digital monitoring and anti-fraud enforcement platform designed "
        "for state mining departments, enforcement squads, and legitimate quarry concessionaires. "
        "Its primary objective is to eliminate illegal mineral transit, fraudulent reuse of statutory transit passes "
        "(e-Rawaana), vehicle overloading, unauthorized truck diversions, and discrepancies between physical mine production "
        "and recorded mineral dispatch.", body_style
    ))

    story.append(Paragraph("<b>The Core Problems it Solves:</b>", h2_style))
    story.append(Paragraph("• <b>Paper &amp; e-Rawaana Recycling:</b> In conventional transit, a single transit pass is frequently reused for multiple trips by trucks shuttling between quarries and crushers. SmartMineGuard links every permit to an active, single-use trip cycle and automatically detects recycling.", bullet_style))
    story.append(Paragraph("• <b>Scale &amp; Manual Weight Manipulation:</b> Operators historically typed net tonnage manually into gate registers, concealing overloaded trucks. SmartMineGuard calculates net payload directly from automated gross and tare weighbridge readings, requiring administrative justification for overrides.", bullet_style))
    story.append(Paragraph("• <b>Illegal Route Diversions:</b> Mineral carriers often deviate into unapproved riverbeds or unmonitored bypass roads to dump illegal mineral. SmartMineGuard compares GPS breadcrumbs against authorized highway corridors in real time.", bullet_style))
    story.append(Paragraph("• <b>Excessive Round Frequency:</b> Rogue vehicles often complete more trips per day than permitted by traffic or concession licenses. SmartMineGuard enforces a strict daily round quota.", bullet_style))
    story.append(Paragraph("• <b>Pithead Production Mismatches:</b> Discrepancies between opening stockpiles, daily quarry blasting, and dispatched mineral are caught automatically through statutory mass-balance equations.", bullet_style))

    story.append(Spacer(1, 4))
    story.append(make_callout(
        "SmartMineGuard is built entirely on <b>deterministic, explainable statutory rules</b>. It does NOT use artificial intelligence, "
        "neural networks, or black-box predictive models. Every violation, alert, and risk penalty reflects a concrete, auditable metric "
        "(e.g., +1.7 MT overload, 2.4 km corridor departure, 18-minute GPS blackout).",
        title="ZERO AI / PURE DETERMINISTIC SURVEILLANCE",
        border_color="#1E3A8A", bg_color="#EFF6FF", text_color="#1E40AF"
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("<b>The Complete End-to-End Mineral Dispatch Workflow:</b>", h2_style))

    # Flowchart table
    flow_data = [
        [Paragraph("<b>Step</b>", tbl_header), Paragraph("<b>Operational Stage</b>", tbl_header), Paragraph("<b>System Action &amp; Statutory Validation</b>", tbl_header)],
        [Paragraph("1", tbl_cell_bold), Paragraph("Permit Issuance", tbl_cell_bold), Paragraph("e-Rawaana pass is issued for a registered truck, validating mineral quota, validity window, and destination.", tbl_cell)],
        [Paragraph("2", tbl_cell_bold), Paragraph("GPS Mine Entry", tbl_cell_bold), Paragraph("Truck crosses the mine geofence. GPS automatically triggers mine entry event and auto-matches the active permit.", tbl_cell)],
        [Paragraph("3", tbl_cell_bold), Paragraph("Pit Loading", tbl_cell_bold), Paragraph("Vehicle payload is loaded at quarry extraction pithead. Trip status transitions to LOADING.", tbl_cell)],
        [Paragraph("4", tbl_cell_bold), Paragraph("Automated Weighment", tbl_cell_bold), Paragraph("Scale captures Gross and Tare. Net mineral weight is calculated automatically (Net = Gross - Tare).", tbl_cell)],
        [Paragraph("5", tbl_cell_bold), Paragraph("Overload Check", tbl_cell_bold), Paragraph("System instantly compares Permitted vs. Weighed Quantity. Flags OVERWEIGHT DISPATCH if weight exceeds permit.", tbl_cell)],
        [Paragraph("6", tbl_cell_bold), Paragraph("Mine Exit &amp; Dispatch", tbl_cell_bold), Paragraph("Truck exits outbound geofence. System authorizes dispatch, starts transit timer, and increments round counter.", tbl_cell)],
        [Paragraph("7", tbl_cell_bold), Paragraph("Transit Surveillance", tbl_cell_bold), Paragraph("Live GPS pings track truck along authorized corridor. Checkpoints log crossings; route deviations flag alerts.", tbl_cell)],
        [Paragraph("8", tbl_cell_bold), Paragraph("Consignee Delivery", tbl_cell_bold), Paragraph("Truck reaches authorized destination (crusher/plant). Trip is marked COMPLETED; permit is officially consumed.", tbl_cell)],
        [Paragraph("9", tbl_cell_bold), Paragraph("Audit &amp; Enforcement", tbl_cell_bold), Paragraph("Violations update truck risk score. Officers review evidence, conduct QR scans, or generate legal dossiers.", tbl_cell)]
    ]
    flow_table = Table(flow_data, colWidths=[35, 140, 335])
    flow_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(flow_table)

    story.append(PageBreak())

    # =========================================================================
    # SECTION 2: CONCEPTUAL DATA RELATIONSHIPS & SECURITY
    # =========================================================================
    story.append(Paragraph("SECTION 2 — CONCEPTUAL DATA RELATIONSHIPS (NO CODE)", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "To operate SmartMineGuard effectively, a user does not need to understand database schemas or technical tables. "
        "Instead, understand how physical mining assets connect in everyday administrative operations:", body_style
    ))

    story.append(Paragraph("<b>The Mineral Transit Hierarchy:</b>", h2_style))
    story.append(Paragraph("1. <b>The Mine Leasehold:</b> The physical quarry or concession where mineral extraction occurs. Every mine has authorized annual production quotas, physical geofences, and stock piles.", bullet_style))
    story.append(Paragraph("2. <b>The Commercial Truck:</b> The heavy vehicle registered to transport mineral. Each truck has an unladen Tare Weight, Maximum Gross Axle Capacity, and an assigned AIS-140 GPS transponder.", bullet_style))
    story.append(Paragraph("3. <b>The Commercial Driver:</b> The licensed transporter operating the truck. Drivers have statutory shift and daily round limits to prevent operator fatigue and excessive rounds.", bullet_style))
    story.append(Paragraph("4. <b>The e-Rawaana Permit:</b> The legal contract authorizing transport of a specific quantity of mineral from a designated mine to an authorized consignee within an active validity window.", bullet_style))
    story.append(Paragraph("5. <b>The Transit Trip:</b> The single physical journey initiated when a truck enters a mine, gets weighed, exits, and travels to destination.", bullet_style))
    story.append(Paragraph("6. <b>The Weighbridge Scale:</b> The certified pithead scale recording gross and tare weights to verify statutory royalties.", bullet_style))
    story.append(Paragraph("7. <b>The Destination:</b> The verified crushing unit, cement plant, or infrastructure buyer authorized to receive the mineral.", bullet_style))

    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>The Enforcement &amp; Audit Hierarchy:</b>", h2_style))
    story.append(Paragraph("• <b>Trip Event $\\longrightarrow$ Detection Engine:</b> As a truck moves, speed, location, and scale data are evaluated against deterministic rules.<br/>"
                           "• <b>Detection $\\longrightarrow$ Risk Score:</b> Detected anomalies add transparent risk points (e.g., +30 for Overweight, +20 for Deviation).<br/>"
                           "• <b>Risk $\\longrightarrow$ Alert Center:</b> High-risk events generate actionable statutory alerts for field squads.<br/>"
                           "• <b>Alert $\\longrightarrow$ Roadside QR Verification:</b> Field officers intercept the truck, scan its physical/digital QR code, and verify live authenticity.<br/>"
                           "• <b>Verification $\\longrightarrow$ Investigation Case File:</b> If fraud is confirmed, an official case is opened, notes are logged, and penalties are levied.<br/>"
                           "• <b>Investigation $\\longrightarrow$ Evidence Dossier PDF:</b> A court-ready PDF dossier containing weighment receipts, breadcrumb maps, and tamper logs is generated.", body_style))

    story.append(Spacer(1, 8))
    story.append(Paragraph("SECTION 3 — SECURITY, PRIVACY &amp; PUBLIC BOUNDARIES", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "SmartMineGuard maintains a strict operational boundary between <b>publicly accessible verification tools</b> "
        "and <b>secured internal command consoles</b>. This segregation is required by state governance standards:", body_style
    ))

    story.append(Paragraph("• <b>Why Public Users Cannot See Surveillance Data:</b> Allowing public access to live GPS positions, route breadcrumbs, officer investigation notes, or truck risk scores would enable illegal mining cartels to evade roadside checkpoints and track enforcement patrols.", bullet_style))
    story.append(Paragraph("• <b>Role Isolation (Multi-Tenant Segregation):</b> A private quarry operator must only see their own mine's trucks, stock, and dispatches. They are strictly prohibited from inspecting neighboring competitors' extraction volumes or state enforcement queues.", bullet_style))
    story.append(Paragraph("• <b>Zero Credential Exposure:</b> System credentials, administrative passwords, and service tokens are never displayed on public pages, login prompts, or field dossiers.", bullet_style))
    story.append(Paragraph("• <b>Permanent Audit Trail:</b> Every sensitive action—including manual weight overrides, permit reconciliations, and case closures—records an immutable log of who acted, when, from where, and why.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 4: PUBLIC LANDING PAGE
    # =========================================================================
    story.append(Paragraph("SECTION 4 — PUBLIC INFORMATION PORTAL ( / )", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "The <b>Public Information Portal</b> is the public-facing entry point accessible to citizens, commercial transporters, "
        "and buyers without logging in. It delivers transparent, statutory mining data while safeguarding sensitive surveillance details.", body_style
    ))

    story.append(Spacer(1, 4))
    story.append(get_image_flowable("01_public_landing.png", target_width=490, max_height=220))
    story.append(Paragraph("Figure 4.1: SmartMineGuard Public Information Portal — Statewide Statistics &amp; Statutory Search", caption_style))

    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>Anatomy of the Public Portal Interface:</b>", h2_style))
    story.append(Paragraph("<b>1 → Public Navigation Header:</b> Provides clear identity as the Directorate of Mines & Geology portal. Features a quick button to the Secure Officer Sign In.", bullet_style))
    story.append(Paragraph("<b>2 → Statewide Operational KPI Cards:</b> Displays real-time aggregated figures backed by the live database: Total Active Mines, Dispatched Trucks in Transit, Valid Transit Permits, and Active Weighbridges.", bullet_style))
    story.append(Paragraph("<b>3 → Interactive Mine Selector:</b> Visitors can select an authorized quarry from a dropdown to inspect its official district, lease code, sanctioned mineral commodity, and compliant dispatched totals.", bullet_style))
    story.append(Paragraph("<b>4 → Statutory Public Verification Search:</b> A citizen verification tool supporting three search types: e-Rawaana Permit Number, Vehicle Registration Number, or ISTP (Inter-State Transit Pass) Number.", bullet_style))

    story.append(Spacer(1, 4))
    story.append(get_image_flowable("02_public_mine_selected.png", target_width=490, max_height=140))
    story.append(Paragraph("Figure 4.2: Public Concession Inspector — Safe leasehold metadata and compliant dispatch tonnage", caption_style))

    story.append(Paragraph("<b>What is Intentionally Concealed from Public View:</b>", h2_style))
    story.append(Paragraph("• Real-time GPS coordinates, vehicle breadcrumb trails, and live movement maps.<br/>"
                           "• Numerical risk scores (0–100) and vehicle violation history.<br/>"
                           "• Internal officer alert queues and active anti-fraud investigations.<br/>"
                           "• Commercial driver phone numbers and operator identity secrets.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 5 & 6: LOGIN & ROLE-BASED ACCESS CONTROL (RBAC)
    # =========================================================================
    story.append(Paragraph("SECTION 5 — LOGIN &amp; AUTHENTICATION ( /login )", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "Authorized personnel gain entry through the <b>Officer &amp; Operator Authentication Portal</b>. "
        "The login screen features administrative identity styling, security disclaimers under Section 43/66 of the IT Act, "
        "and helpdesk contact references.", body_style
    ))

    story.append(Spacer(1, 4))
    story.append(get_image_flowable("03_login_screen.png", target_width=380, max_height=180))
    story.append(Paragraph("Figure 5.1: Secured Authentication Portal — Zero exposed demo credentials and statutory IT Act warning", caption_style))

    story.append(Paragraph("<b>How the System Governs Your Session:</b>", h2_style))
    story.append(Paragraph("When an authorized user signs in, the system checks their service credentials and automatically redirects them to their specialized workspace: Administrators enter the <b>Admin Command Center</b>, Field Inspectors enter the <b>Officer Enforcement Center</b>, and Lease Managers enter their <b>Mine Operations Console</b>.", body_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 6 — ROLE-BASED ACCESS CONTROL (RBAC) MATRIX", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "Access permissions are enforced strictly at the server level to prevent unauthorized data inspection or cross-tenant tampering:", body_style
    ))

    rbac_data = [
        [Paragraph("<b>Functional Capability / Section</b>", tbl_header), Paragraph("<b>ADMIN (Director)</b>", tbl_header), Paragraph("<b>OFFICER (Squad)</b>", tbl_header), Paragraph("<b>OPERATOR (Mine)</b>", tbl_header)],
        [Paragraph("System Overview & State KPI Cards", tbl_cell_bold), Paragraph("Full State-Wide", tbl_cell), Paragraph("Surveillance Focus", tbl_cell), Paragraph("Own Lease Only", tbl_cell)],
        [Paragraph("Live GIS Map & Route Reconstruction", tbl_cell_bold), Paragraph("Full Access", tbl_cell), Paragraph("Full Access", tbl_cell), Paragraph("Own Fleet Only", tbl_cell)],
        [Paragraph("Alerts Center & Risk Scores", tbl_cell_bold), Paragraph("Full Access", tbl_cell), Paragraph("Full Access & Triage", tbl_cell), Paragraph("Restricted / None", tbl_cell)],
        [Paragraph("Investigation Cases & Dossier Generation", tbl_cell_bold), Paragraph("Full Authority", tbl_cell), Paragraph("Full Authority", tbl_cell), Paragraph("403 Forbidden", tbl_cell)],
        [Paragraph("Roadside QR Code Mobile Verification", tbl_cell_bold), Paragraph("Full Access", tbl_cell), Paragraph("Primary Tool", tbl_cell), Paragraph("403 Forbidden", tbl_cell)],
        [Paragraph("Automated Weighbridge Scale Overrides", tbl_cell_bold), Paragraph("Authorized with Reason", tbl_cell), Paragraph("Authorized with Reason", tbl_cell), Paragraph("403 Forbidden", tbl_cell)],
        [Paragraph("e-Rawaana Permit Issuance", tbl_cell_bold), Paragraph("Full Access", tbl_cell), Paragraph("Read Only", tbl_cell), Paragraph("Own Lease Only", tbl_cell)],
        [Paragraph("Stock & Daily Production Entries", tbl_cell_bold), Paragraph("Full Access", tbl_cell), Paragraph("Read Only", tbl_cell), Paragraph("Own Lease Only", tbl_cell)],
        [Paragraph("Master Data CRUD (Mines, Checkpoints)", tbl_cell_bold), Paragraph("Full Authority", tbl_cell), Paragraph("403 Forbidden", tbl_cell), Paragraph("403 Forbidden", tbl_cell)],
        [Paragraph("User Badge & Account Management", tbl_cell_bold), Paragraph("Full Authority", tbl_cell), Paragraph("403 Forbidden", tbl_cell), Paragraph("403 Forbidden", tbl_cell)]
    ]
    rbac_table = Table(rbac_data, colWidths=[160, 115, 115, 120])
    rbac_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(rbac_table)

    story.append(PageBreak())

    # =========================================================================
    # SECTION 7: ADMIN COMMAND CENTER
    # =========================================================================
    story.append(Paragraph("SECTION 7 — ADMIN COMMAND CENTER ( /dashboard )", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "The <b>Admin Command Center</b> is the central operational hub for executive mining authorities. "
        "It aggregates statewide mineral movement, monitors statutory dispatch ceilings, and flags anomalous production imbalances.", body_style
    ))

    story.append(Spacer(1, 4))
    story.append(get_image_flowable("04_admin_dashboard.png", target_width=490, max_height=210))
    story.append(Paragraph("Figure 7.1: Administrator Command Center — Daily dispatch quotas, statutory alerts, and multi-mine KPIs", caption_style))

    story.append(Paragraph("<b>Key Dashboard Metric Cards Explained:</b>", h2_style))
    story.append(Paragraph("• <b>Active Concessions &amp; Active Trucks:</b> Real-time tally of operational quarry leases and heavy transport vehicles currently in transit.", bullet_style))
    story.append(Paragraph("• <b>Dispatched Today vs. Permitted Total:</b> Total metric tonnage moved today compared to authorized transit quota across all active e-Rawaana passes.", bullet_style))
    story.append(Paragraph("• <b>Total Excess Tonnage Detected:</b> Sum of all overloaded weight captured by pithead weighbridges across the state (+11.0 MT overload penalty tracking).", bullet_style))
    story.append(Paragraph("• <b>Critical Enforcement Alerts:</b> High-priority violations requiring immediate squad intervention (e.g. Sabi riverbed deviations, signal blackouts).", bullet_style))

    story.append(Spacer(1, 4))
    story.append(make_callout(
        "<b>Today's Dispatch Control &amp; Round Quota Widget:</b> Shows planned vs. actual dispatch tonnage and truck round progress. "
        "For example: Planned = 500.0 MT | Dispatched = 327.5 MT | Remaining = 172.5 MT | Allowed Rounds = 20 | Completed = 14 | Remaining = 6.",
        title="TODAY'S DISPATCH PLANNING AUDIT",
        border_color="#0F3826", bg_color="#F0FDF4", text_color="#166534"
    ))

    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>Statutory Production-Dispatch Mismatch Banner:</b>", h2_style))
    story.append(Paragraph(
        "When physical extraction records at a quarry do not align with outbound weighbridge dispatches beyond a 50 MT tolerance, "
        "the Admin dashboard immediately presents a prominent crimson warning banner: <b>PRODUCTION-DISPATCH MISMATCH DETECTED</b>. "
        "This prevents leaseholders from dispatching unrecorded mineral or hoarding stockpiles without statutory reporting.", body_style
    ))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 8 & 9: OPERATOR & OFFICER DASHBOARDS
    # =========================================================================
    story.append(Paragraph("SECTION 8 — OPERATOR DASHBOARD", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "The <b>Operator Dashboard</b> is customized specifically for quarry managers and leaseholders. "
        "It provides pithead operational clarity without exposing competitor data or police squad surveillance.", body_style
    ))

    story.append(Spacer(1, 4))
    story.append(get_image_flowable("21_operator_dashboard.png", target_width=490, max_height=200))
    story.append(Paragraph("Figure 8.1: Leaseholder Pithead Dashboard — Stock reconciliation, daily dispatch balance, and fleet queue", caption_style))

    story.append(Paragraph("<b>What an Operator Inspects During a Daily Shift:</b>", h2_style))
    story.append(Paragraph("1. <b>Leasehold Stock Balance:</b> Opening Stock (3,500 MT) + Today's Blasting (500 MT) - Dispatched (0 MT) = Expected Closing Stock (4,000 MT).", bullet_style))
    story.append(Paragraph("2. <b>Daily Dispatch Balance:</b> Tracking remaining daily quota to ensure the quarry does not exceed its environmental clearance limits.", bullet_style))
    story.append(Paragraph("3. <b>Truck-Wise Dispatch Ledger:</b> Verifying which authorized vehicles have arrived inside the mine, which are loading, and which have completed their weighment.", bullet_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 9 — OFFICER ENFORCEMENT COMMAND CENTER", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "The <b>Officer Dashboard</b> is designed exclusively for field squads, flying squads, and border checkpoint teams "
        "to rapidly detect, prioritize, and intercept fraudulent mineral transport vehicles.", body_style
    ))

    story.append(Spacer(1, 4))
    story.append(get_image_flowable("20_officer_dashboard.png", target_width=490, max_height=200))
    story.append(Paragraph("Figure 9.1: Officer Enforcement Screen — High-Risk Interception Queue &amp; Rapid Dossier Generation", caption_style))

    story.append(Paragraph("<b>The Officer's Rapid Action Workflow:</b>", h2_style))
    story.append(Paragraph("• <b>High-Risk Interception Queue:</b> Vehicles with critical risk scores (e.g. HR26AB1234 at 100/100) appear at the top with direct action buttons.", bullet_style))
    story.append(Paragraph("• <b>Track Truck:</b> Instantly jumps to the Live GIS Map centered on the vehicle's coordinates with corridor reconstruction.", bullet_style))
    story.append(Paragraph("• <b>Verify QR:</b> Directs to the roadside scanning tool for physical pass authenticity validation.", bullet_style))
    story.append(Paragraph("• <b>Generate Dossier:</b> Instantly compiles and downloads an official court-ready investigation PDF.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 10 & 11: LIVE GIS MAP & ROUTE RECONSTRUCTION
    # =========================================================================
    story.append(Paragraph("SECTION 10 — LIVE GIS MAP &amp; SURVEILLANCE ( /map )", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "The <b>Live GIS Map</b> is the tactical geospatial surveillance screen. Built with Leaflet GIS, "
        "it monitors commercial mineral trucks across verified highway corridors, mining leaseholds, and border checkpoints.", body_style
    ))

    story.append(Spacer(1, 4))
    story.append(get_image_flowable("05_live_gis_map.png", target_width=490, max_height=210))
    story.append(Paragraph("Figure 10.1: Live GIS Canvas — Real-time vehicle markers, concession geofences, and transport corridors", caption_style))

    story.append(Paragraph("<b>Map Legend &amp; Color Coding:</b>", h2_style))
    story.append(Paragraph("• <b>Truck Markers:</b> Color-coded by real-time calculated risk: Green (LOW: 0–30), Amber (MEDIUM: 31–60), Orange (HIGH: 61–80), Red (CRITICAL: 81–100).", bullet_style))
    story.append(Paragraph("• <b>Green Polygonal Geofences:</b> Authorized mining extraction leaseholds (e.g. Aravalli Quartzite Quarry Block A).", bullet_style))
    story.append(Paragraph("• <b>Blue Route Corridors:</b> Sanctioned transit highways (NH-48 / SH-14) authorized under mineral transport rules.", bullet_style))
    story.append(Paragraph("• <b>Red Restricted Zones:</b> Environmentally sensitive or restricted riverbeds (e.g. Sabi Riverbed) where entry triggers immediate high-severity alerts.", bullet_style))
    story.append(Paragraph("• <b>Purple Markers:</b> Official state border checkpoints, outbound scales, and toll barriers.", bullet_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 11 — ROUTE RECONSTRUCTION &amp; CORRIDOR DEVIATION", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "When an officer clicks on any vehicle in the fleet roster, SmartMineGuard reconstructs the complete historical "
        "and authorized journey using dual-polyline visual treatment:", body_style
    ))

    story.append(Spacer(1, 4))
    story.append(get_image_flowable("06_route_reconstruction.png", target_width=490, max_height=210))
    story.append(Paragraph("Figure 11.1: Route Reconstruction — Solid Emerald Breadcrumb Track vs. Dashed Authorized Corridor", caption_style))

    story.append(Paragraph("<b>How Route Deviation is Detected Visually:</b>", h2_style))
    story.append(Paragraph("• <b>Authorized Transport Corridor (Dashed Gold/Blue Line):</b> Represents the legal, sanctioned transit path between source quarry and destination consignee.", bullet_style))
    story.append(Paragraph("• <b>Actual GPS Breadcrumbs (Solid Emerald Track):</b> The chronological historical GPS positions reported by the truck's transponder.", bullet_style))
    story.append(Paragraph("• <b>Corridor Departure Flag:</b> When the breadcrumbs diverge from the authorized corridor by more than 500 meters, the system flags <b>ROUTE DEVIATION</b>, highlights the departure point, and elevates vehicle risk.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 12 & 13: CHRONOLOGICAL TIMELINE & TRUCK FLEET
    # =========================================================================
    story.append(Paragraph("SECTION 12 — CHRONOLOGICAL TRIP AUDIT TIMELINE", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "Every transit journey creates an immutable, timestamped chronological milestone timeline. "
        "This feed appears in the Live Map telemetry inspector drawer and the Truck Detail inspector:", body_style
    ))

    timeline_data = [
        [Paragraph("<b>Timestamp</b>", tbl_header), Paragraph("<b>Milestone Event</b>", tbl_header), Paragraph("<b>Statutory Audit Meaning</b>", tbl_header)],
        [Paragraph("08:12", tbl_cell_bold), Paragraph("Entered Mine", tbl_cell_bold), Paragraph("Automated GPS geofence entry detected at Quarry Block A. Geofence dwell confirmed.", tbl_cell)],
        [Paragraph("08:15", tbl_cell_bold), Paragraph("Permit Matched", tbl_cell_bold), Paragraph("System automatically associates active e-Rawaana SMG-2026-00125 for this vehicle.", tbl_cell)],
        [Paragraph("08:22", tbl_cell_bold), Paragraph("Loading Started", tbl_cell_bold), Paragraph("Quarry excavator commences loading aggregate into truck tipper.", tbl_cell)],
        [Paragraph("08:28", tbl_cell_bold), Paragraph("Scale Weighed", tbl_cell_bold), Paragraph("Calibrated weighbridge WB-ARA-01 records Gross = 35.8 MT, Tare = 11.2 MT.", tbl_cell)],
        [Paragraph("08:29", tbl_cell_bold), Paragraph("Net Payload Checked", tbl_cell_bold), Paragraph("Net weight calculated automatically as 24.6 MT. Verified compliant against 24.0 MT permit.", tbl_cell)],
        [Paragraph("08:34", tbl_cell_bold), Paragraph("Dispatch Cleared", tbl_cell_bold), Paragraph("Outbound gate pass approved. Trip status transitions to DISPATCHED.", tbl_cell)],
        [Paragraph("08:42", tbl_cell_bold), Paragraph("Exited Mine (Round #1)", tbl_cell_bold), Paragraph("Truck crosses outbound geofence. Completed round count increments to 1.", tbl_cell)],
        [Paragraph("09:25", tbl_cell_bold), Paragraph("GPS Blackout Detected", tbl_cell_bold), Paragraph("Transponder stops transmitting for 18 minutes near riverbed bypass. Alert emitted.", tbl_cell)],
        [Paragraph("10:05", tbl_cell_bold), Paragraph("Signal Restored", tbl_cell_bold), Paragraph("GPS telemetry re-acquired at Checkpoint CP-KOT-01. Checkpoint crossing logged.", tbl_cell)]
    ]
    timeline_table = Table(timeline_data, colWidths=[65, 140, 305])
    timeline_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(timeline_table)

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 13 — TRUCK FLEET &amp; MULTI-PERIOD AUDIT ( /trucks )", h1_style))
    story.append(make_section_divider())

    story.append(get_image_flowable("07_trucks_fleet.png", target_width=490, max_height=180))
    story.append(Paragraph("Figure 13.1: Trucks Fleet Management — Vehicle registration, RFID, status, and cumulative tonnage totals", caption_style))

    story.append(Spacer(1, 4))
    story.append(get_image_flowable("08_truck_detail.png", target_width=490, max_height=200))
    story.append(Paragraph("Figure 13.2: Truck Detail Inspector — Geofence round quota card, multi-period payload profile, and timeline", caption_style))

    story.append(Paragraph("<b>The Multi-Period Cumulative Surveillance Card Explained:</b>", h2_style))
    story.append(Paragraph("• <b>Today's Audit:</b> Trips completed today, Dispatched MT, Permitted MT, and Daily Excess payload.<br/>"
                           "• <b>This Week's Audit:</b> 7-day cumulative payload moved and total excess violations recorded.<br/>"
                           "• <b>This Month's Audit:</b> 30-day lifetime tonnage and chronic overload totals (+186.3 MT lifetime excess).<br/>"
                           "• <b>Enforcement Value:</b> Allows directors to immediately identify repeat commercial offenders operating under multiple shell transport companies.", body_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 14 & 15: e-RAWAANA PERMITS & TRANSIT TRIPS
    # =========================================================================
    story.append(Paragraph("SECTION 14 — e-RAWAANA TRANSIT PERMITS ( /permits )", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "The <b>e-Rawaana Passes Ledger</b> manages statutory mineral transit permits issued under State Mineral Concession Rules. "
        "Every pass represents an official legal authorization for a specific quantity of mineral.", body_style
    ))

    story.append(Spacer(1, 4))
    story.append(get_image_flowable("09_permits_ledger.png", target_width=490, max_height=200))
    story.append(Paragraph("Figure 14.1: e-Rawaana Transit Permits Ledger — Pass numbers, vehicle assignment, validities, and QR tools", caption_style))

    story.append(Spacer(1, 4))
    story.append(get_image_flowable("10_permit_qr_modal.png", target_width=320, max_height=190))
    story.append(Paragraph("Figure 14.2: Official Cryptographic QR Pass Dialog — Scannable token for roadside enforcement", caption_style))

    story.append(Paragraph("<b>Statutory Permit States Explained:</b>", h2_style))
    story.append(Paragraph("• <b>ISSUED / ACTIVE:</b> Valid permit ready for truck arrival and loading.<br/>"
                           "• <b>TRUCK_ARRIVED:</b> Automatically assigned when truck enters the mine geofence.<br/>"
                           "• <b>WEIGHED:</b> Weighbridge measurement captured; payload verified compliant.<br/>"
                           "• <b>DISPATCHED:</b> Truck has departed mine; transit journey actively monitored.<br/>"
                           "• <b>COMPLETED:</b> Cargo delivered to authorized consignee; permit permanently consumed.<br/>"
                           "• <b>RECONCILIATION_REQUIRED:</b> Flagged when an old unused permit conflicts with a new trip. Cancellation requires authorized role action.", body_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 15 — TRANSIT TRIPS LEDGER ( /trips )", h1_style))
    story.append(make_section_divider())

    story.append(get_image_flowable("11_transit_trips.png", target_width=490, max_height=190))
    story.append(Paragraph("Figure 15.1: Dispatched Transit Trips — Round numbers, average speeds, risk levels, and timeline audit links", caption_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 16 & 17: AUTOMATED WEIGHBRIDGE & STOCK RECONCILIATION
    # =========================================================================
    story.append(Paragraph("SECTION 16 — AUTOMATED WEIGHBRIDGE &amp; SCALE OVERRIDES", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "A major security feature in SmartMineGuard is the <b>elimination of normal manual weight typing</b>. "
        "In routine dispatch operations, operators cannot type or edit the net mineral weight.", body_style
    ))

    story.append(Paragraph("<b>The Automated Scale Measurement Equation:</b>", h2_style))
    story.append(make_callout(
        "<b>Gross Weight</b> (e.g. 35.8 MT) - <b>Tare Weight</b> (e.g. 11.2 MT) = <b>Net Mineral Payload</b> (24.6 MT).<br/>"
        "The system immediately evaluates: <b>Excess Payload</b> = Actual Net Weight (24.6 MT) - Permitted Weight (24.0 MT) = <b>+0.6 MT Overload</b>.<br/>"
        "If Actual &gt; Permitted, the system emits an automatic <b>OVERWEIGHT DISPATCH</b> violation alert (+30 risk points).",
        title="AUTOMATED SENSOR WEIGHMENT MATH",
        border_color="#0F3826", bg_color="#F0FDF4", text_color="#166534"
    ))

    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>Authorized Manual Override Protocol:</b>", h2_style))
    story.append(Paragraph(
        "If an extraordinary scale calibration error occurs, only an <b>Administrator or Officer</b> can submit a manual weight override. "
        "The system enforces mandatory justification, records the original value, the corrected value, officer ID, and timestamp, "
        "labels the record <b>MANUAL OVERRIDE</b>, and adds <b>+15 risk points</b> to the truck's profile.", body_style
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 17 — PITHEAD STOCK &amp; PRODUCTION MASS-BALANCE", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "SmartMineGuard continuously balances quarry stockpiles using a statutory mass-balance formula:", body_style
    ))

    story.append(make_callout(
        "$$\\text{Expected Closing Stock} = \\text{Opening Stock} + \\text{Today's Blasting Production} - \\text{Today's Total Dispatches}$$<br/>"
        "<b>Example:</b> Opening Stock (1,250 MT) + Today's Production (500 MT) - Today's Dispatch (420 MT) = <b>Expected Closing Stock (1,330 MT)</b>.<br/>"
        "If recorded physical stock differs from expected closing stock by more than the configured 50 MT statutory tolerance, "
        "a <b>PRODUCTION-DISPATCH MISMATCH</b> alert is raised immediately.",
        title="STATUTORY MASS-BALANCE EQUATION",
        border_color="#B45309", bg_color="#FEF3C7", text_color="#92400E"
    ))

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 18 — TRUCK TRIP COUNTER &amp; COMMERCIAL DISPATCH", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "A truck trip is tracked as: <b>Mine Geofence Entry $\\longrightarrow$ Weighment $\\longrightarrow$ Mine Geofence Exit</b>. "
        "In commercial mining operations, trucks operate under unrestricted dispatch with continuous trip sequencing and no round limit.", body_style
    ))

    story.append(Paragraph("• <b>Trip Ledger Display:</b> Continuous Trip Sequence | Trips Completed Today | Active Trip Status | Net Dispatched Payload.<br/>"
                           "• <b>Fleet Dispatch Telemetry:</b> Trucks make as many rounds as operationally viable, with each trip cryptographically logged and reconciled against active concession mineral quotas.", body_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 19 & 20: DETECTION RULES & EXPLAINABLE RISK ENGINE
    # =========================================================================
    story.append(Paragraph("SECTION 19 — DETERMINISTIC DETECTION ENGINE (11 RULES)", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "SmartMineGuard evaluates transit telemetry against 11 transparent statutory rules. "
        "Every violation provides exact mathematical justification without opaque AI claims:", body_style
    ))

    rules_data = [
        [Paragraph("<b>Statutory Rule Name</b>", tbl_header), Paragraph("<b>Trigger Condition &amp; Data Compared</b>", tbl_header), Paragraph("<b>Severity</b>", tbl_header), Paragraph("<b>Risk Pts</b>", tbl_header)],
        [Paragraph("1. Overweight Dispatch", tbl_cell_bold), Paragraph("Scale Net Weight exceeds e-Rawaana permitted tonnage.", tbl_cell), Paragraph("CRITICAL", tbl_cell), Paragraph("+30", tbl_cell)],
        [Paragraph("2. Route Corridor Deviation", tbl_cell_bold), Paragraph("Truck location departs from authorized highway corridor by &gt;500m.", tbl_cell), Paragraph("HIGH", tbl_cell), Paragraph("+20", tbl_cell)],
        [Paragraph("3. GPS Signal Blackout", tbl_cell_bold), Paragraph("AIS-140 GPS pings cease for &gt;15 minutes while in transit.", tbl_cell), Paragraph("HIGH", tbl_cell), Paragraph("+20", tbl_cell)],
        [Paragraph("4. e-Rawaana Permit Reuse", tbl_cell_bold), Paragraph("Same permit used across multiple vehicles or repeated trips.", tbl_cell), Paragraph("CRITICAL", tbl_cell), Paragraph("+35", tbl_cell)],
        [Paragraph("5. Vehicle-Permit Mismatch", tbl_cell_bold), Paragraph("Truck enters mine with a permit assigned to a different registration.", tbl_cell), Paragraph("CRITICAL", tbl_cell), Paragraph("+30", tbl_cell)],
        [Paragraph("6. Unauthorized Mine Entry", tbl_cell_bold), Paragraph("Truck enters quarry geofence with no active or valid permit.", tbl_cell), Paragraph("HIGH", tbl_cell), Paragraph("+25", tbl_cell)],
        [Paragraph("7. Excessive Trip Frequency", tbl_cell_bold), Paragraph("Completed rounds today exceed daily allowed round quota.", tbl_cell), Paragraph("HIGH", tbl_cell), Paragraph("+25", tbl_cell)],
        [Paragraph("8. Impossible Transit Speed", tbl_cell_bold), Paragraph("Vehicle reaches destination at mathematically impossible speed (&gt;90 km/h).", tbl_cell), Paragraph("CRITICAL", tbl_cell), Paragraph("+30", tbl_cell)],
        [Paragraph("9. Production Mismatch", tbl_cell_bold), Paragraph("Dispatched mineral exceeds recorded pit extraction beyond tolerance.", tbl_cell), Paragraph("HIGH", tbl_cell), Paragraph("+25", tbl_cell)],
        [Paragraph("10. Manual Weight Override", tbl_cell_bold), Paragraph("Scale reading was manually altered rather than automated sensor capture.", tbl_cell), Paragraph("MEDIUM", tbl_cell), Paragraph("+15", tbl_cell)],
        [Paragraph("11. Quota Permit Blocked", tbl_cell_bold), Paragraph("Attempted pass generation for vehicle that already completed daily rounds.", tbl_cell), Paragraph("HIGH", tbl_cell), Paragraph("+25", tbl_cell)]
    ]
    rules_table = Table(rules_data, colWidths=[130, 240, 70, 70])
    rules_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(rules_table)

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 20 — EXPLAINABLE RISK SCORING (0–100 SCALE)", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "Risk scores represent the cumulative severity of detected violations for each truck and trip. "
        "The system never displays 'AI detected risk'. Instead, it shows transparent mathematical breakdowns:", body_style
    ))

    score_data = [
        [Paragraph("<b>Risk Tier</b>", tbl_header), Paragraph("<b>Score Range</b>", tbl_header), Paragraph("<b>Visual Badge</b>", tbl_header), Paragraph("<b>Operational Enforcement Action</b>", tbl_header)],
        [Paragraph("LOW", tbl_cell_bold), Paragraph("0 to 30", tbl_cell), Paragraph("Green Badge", tbl_cell), Paragraph("Compliant journey. Normal transit clearance; automated green channel.", tbl_cell)],
        [Paragraph("MEDIUM", tbl_cell_bold), Paragraph("31 to 60", tbl_cell), Paragraph("Amber Badge", tbl_cell), Paragraph("Minor anomaly (e.g. speed warning, manual override). Monitor on map.", tbl_cell)],
        [Paragraph("HIGH", tbl_cell_bold), Paragraph("61 to 80", tbl_cell), Paragraph("Orange Badge", tbl_cell), Paragraph("Route departure or signal loss. Checkpoint squads alerted for physical inspection.", tbl_cell)],
        [Paragraph("CRITICAL", tbl_cell_bold), Paragraph("81 to 100", tbl_cell), Paragraph("Red Pulsing Badge", tbl_cell), Paragraph("Active fraud confirmed (Overload + Diversion). Immediate squad interception.", tbl_cell)]
    ]
    score_table = Table(score_data, colWidths=[80, 80, 90, 260])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(score_table)

    story.append(PageBreak())

    # =========================================================================
    # SECTION 21 & 22: ALERTS & INVESTIGATIONS
    # =========================================================================
    story.append(Paragraph("SECTION 21 — ALERTS CENTER &amp; TRIAGE ( /alerts )", h1_style))
    story.append(make_section_divider())

    story.append(get_image_flowable("12_alerts_center.png", target_width=490, max_height=200))
    story.append(Paragraph("Figure 21.1: Alerts Center — Severity filters, violation descriptions, risk metrics, and quick action triage", caption_style))

    story.append(Paragraph("<b>Alert Lifecycle Stages:</b>", h2_style))
    story.append(Paragraph("• <b>NEW:</b> Alert generated by detection engine; awaiting officer acknowledgment.<br/>"
                           "• <b>ACKNOWLEDGED:</b> Field squad has seen the alert and dispatched a patrol unit.<br/>"
                           "• <b>UNDER INVESTIGATION:</b> Formal case opened; evidence attached and vehicle detained.<br/>"
                           "• <b>RESOLVED / CLOSED:</b> Penalty collected or statutory clearance issued; case closed.", body_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 22 — INVESTIGATIONS &amp; CASE FILES ( /investigations )", h1_style))
    story.append(make_section_divider())

    story.append(get_image_flowable("13_investigations.png", target_width=490, max_height=200))
    story.append(Paragraph("Figure 22.1: Statutory Investigations — Case IDs, lead officers, findings, decision status, and evidence dossiers", caption_style))

    story.append(Paragraph("<b>Investigation Fields &amp; Legal Enforcement Actions:</b>", h2_style))
    story.append(Paragraph("• <b>Case ID:</b> Unique statutory identifier (e.g. SMG-2026-00041) referenced in legal notices.<br/>"
                           "• <b>Initial Findings:</b> System-compiled evidence summary (overload tonnage, corridor deviation point).<br/>"
                           "• <b>Officer Notes:</b> Field inspector's physical observations recorded during vehicle inspection.<br/>"
                           "• <b>Penalty Amount (INR):</b> Compounding fine assessed under MMDR Act rules.<br/>"
                           "• <b>Evidence Dossier PDF:</b> Direct action button to generate the complete evidence package.", body_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 23 & 24: QR VERIFICATION & EVIDENCE REPORTS
    # =========================================================================
    story.append(Paragraph("SECTION 23 — OFFICER ROADSIDE QR VERIFICATION ( /verify-qr )", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "The <b>QR Verification Module</b> is built for mobile tablets and smartphones used by flying squads at roadside checkpoints. "
        "It eliminates forged paper passes by performing instantaneous cryptographic verification:", body_style
    ))

    story.append(Spacer(1, 4))
    story.append(get_image_flowable("14_qr_verification.png", target_width=420, max_height=170))
    story.append(Paragraph("Figure 23.1: Officer Mobile QR Verification — Camera scanner &amp; instant permit validation tool", caption_style))

    story.append(Paragraph("<b>How Roadside Verification Operates:</b>", h2_style))
    story.append(Paragraph("1. Inspector aims camera at the driver's printed or mobile e-Rawaana QR code.<br/>"
                           "2. System decrypts the payload: Permit Number, Assigned Truck, Mineral, and Permitted Tonnage.<br/>"
                           "3. System compares the pass with the active database record. If the pass is expired, reused, or registered to another truck, an immediate <b>CRITICAL FORGERY WARNING</b> is displayed on screen.", body_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 24 — REPORTS &amp; EVIDENCE DOSSIERS ( /reports )", h1_style))
    story.append(make_section_divider())

    story.append(get_image_flowable("16_reports_dossiers.png", target_width=490, max_height=190))
    story.append(Paragraph("Figure 24.1: Reports &amp; Dossiers Repository — Printable statutory PDF investigation packages", caption_style))

    story.append(Paragraph("<b>Contents of the Generated Evidence Dossier PDF:</b>", h2_style))
    story.append(Paragraph("• Official State Directorate Crest and statutory Case Identification Header.<br/>"
                           "• Registered Vehicle Specifications, RFID tag, AIS-140 IMEI, and Transporter details.<br/>"
                           "• Outbound Scale Weighment Audit Receipt with Gross, Tare, and calculated Net Payload.<br/>"
                           "• Complete Chronological Milestone Ledger with verified entry and exit timestamps.<br/>"
                           "• High-resolution Leaflet Route Map showing departure coordinates and deviation distance.<br/>"
                           "• Cryptographic Verification QR Code for court and judicial validation.", body_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 25 & 26: ANALYTICS & MASTER DATA MANAGEMENT
    # =========================================================================
    story.append(Paragraph("SECTION 25 — ANALYTICS DASHBOARD ( /analytics )", h1_style))
    story.append(make_section_divider())

    story.append(get_image_flowable("15_analytics_dashboard.png", target_width=490, max_height=190))
    story.append(Paragraph("Figure 25.1: Analytics Dashboard — Mineral transit volume, risk distribution, and compliance trends", caption_style))

    story.append(Paragraph("<b>Analytics Charts Explained:</b>", h2_style))
    story.append(Paragraph("• <b>Mineral Dispatch Volume by Quarry:</b> Bar chart comparing output across active state leaseholds.<br/>"
                           "• <b>Fleet Risk Level Distribution:</b> Donut chart showing percentage of Low, Medium, High, and Critical vehicles.<br/>"
                           "• <b>Hourly Violation Frequency:</b> Trendline identifying high-risk time windows (e.g. night-time blackouts).", body_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 26 — MASTER DATA MANAGEMENT ( /admin/data )", h1_style))
    story.append(make_section_divider())

    story.append(get_image_flowable("17_master_data_console.png", target_width=490, max_height=190))
    story.append(Paragraph("Figure 26.1: Master Data Console — Tabs for Mines, Trucks, Drivers, Passes, Trips, Weighbridges, Checkpoints", caption_style))

    story.append(Paragraph("<b>All Master Data Registry Tabs Explained:</b>", h2_style))
    story.append(Paragraph("• <b>Mines &amp; Leases:</b> Official concession registry with boundary coordinates and annual extraction quotas.<br/>"
                           "• <b>Trucks Fleet:</b> Commercial carriers with RFID, tare weight, and daily allowed round quotas.<br/>"
                           "• <b>Drivers:</b> Commercial driver licenses, contact phones, and assigned vehicles.<br/>"
                           "• <b>e-Rawaana Passes:</b> Statutory transit authorizations with validity hours and buyer destinations.<br/>"
                           "• <b>Transit Trips:</b> Active and completed journeys with odometer and speed telemetry.<br/>"
                           "• <b>Weighbridges:</b> Certified pithead scales with operator names and calibration status.<br/>"
                           "• <b>Destinations &amp; Checkpoints:</b> Verified crusher receiving points and border monitoring posts.<br/>"
                           "• <b>Stock &amp; Production:</b> Daily pithead extraction logs and closing inventory balances.", body_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 27 & 28: QUOTA GUARDRAIL & USER MANAGEMENT
    # =========================================================================
    story.append(Paragraph("SECTION 27 — CONTINUOUS DISPATCH: UNRESTRICTED COMMERCIAL TRANSIT", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "To support real-world mining productivity where trucks make continuous rounds throughout the operational shift, "
        "SmartMineGuard implements an <b>unrestricted commercial dispatch model</b>. Trucks and drivers operate without artificial daily round caps:", body_style
    ))

    story.append(Spacer(1, 4))
    story.append(get_image_flowable("18_modal_add_permit.png", target_width=440, max_height=210))
    story.append(Paragraph("Figure 27.1: Issue e-Rawaana Modal — Live vehicle selection displaying active commercial transit status", caption_style))

    story.append(Paragraph("<b>How Continuous Commercial Dispatch Operates:</b>", h2_style))
    story.append(Paragraph("1. <b>Continuous Vehicle Authorization:</b> The vehicle dropdown displays active trucks ready for dispatch: e.g. <i>'RJ14GA5521 • Vikram Singh (Active Commercial Fleet)'</i>.<br/>"
                           "2. <b>Dynamic Trip Sequencing:</b> Each newly issued transit pass automatically advances the truck's cumulative trip count and updates mine stock ledger in real-time.<br/>"
                           "3. <b>Unrestricted Permit Issuance:</b> Operators can issue consecutive permits for any registered vehicle without artificial daily quota limits.<br/>"
                           "4. <b>Comprehensive Audit Trail:</b> Every trip is individually cryptographically verified, timestamped, and reconciled against mineral lease reserve quotas.", body_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 28 — USER &amp; BADGE MANAGEMENT ( /admin/users )", h1_style))
    story.append(make_section_divider())

    story.append(get_image_flowable("19_user_management.png", target_width=490, max_height=190))
    story.append(Paragraph("Figure 28.1: Administrative User Console — Roles, departmental badge numbers, and official contact credentials", caption_style))

    story.append(Paragraph("<b>User Attributes Governed by Administrator:</b>", h2_style))
    story.append(Paragraph("• <b>Username &amp; Role:</b> Controls access level (ADMIN, OFFICER, or OPERATOR).<br/>"
                           "• <b>Official Department:</b> E.g. Directorate of Mines & Geology, Mining Enforcement Squad Zone 4.<br/>"
                           "• <b>Badge Number:</b> Formal statutory service badge (e.g. DMG-HQ-01, MES-Z4-409).<br/>"
                           "• <b>Security Notice:</b> Passwords are never revealed on screen; password resets generate encrypted hashes.", body_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 29 & 30: COMPLETE TRUCK JOURNEY & 6 CASE STUDIES
    # =========================================================================
    story.append(Paragraph("SECTION 29 — ONE COMPLETE TRUCK JOURNEY (END-TO-END)", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "To see how all modules interact in the real world, follow the complete journey of truck <b>HR26AB1234</b> "
        "transporting Quartzite Aggregate from <b>Aravalli Quarry Block A</b> to <b>Bhiwadi Crushing Zone</b>:", body_style
    ))

    journey_steps = [
        [Paragraph("<b>Stage</b>", tbl_header), Paragraph("<b>Physical Operational Event</b>", tbl_header), Paragraph("<b>SmartMineGuard Automated Response</b>", tbl_header)],
        [Paragraph("1", tbl_cell_bold), Paragraph("Pass Generation", tbl_cell), Paragraph("Operator issues e-Rawaana SMG-2026-00125 for 24.0 MT Quartzite. System verifies round quota (0/4 used).", tbl_cell)],
        [Paragraph("2", tbl_cell_bold), Paragraph("Quarry Entry", tbl_cell), Paragraph("Truck crosses geofence. GPS confirms entry; permit status changes to TRUCK_ARRIVED. Operator button not needed.", tbl_cell)],
        [Paragraph("3", tbl_cell_bold), Paragraph("Loading", tbl_cell), Paragraph("Excavator fills tipper. Status changes to LOADING; timeline logs start time.", tbl_cell)],
        [Paragraph("4", tbl_cell_bold), Paragraph("Automated Weighment", tbl_cell), Paragraph("Weighbridge records Gross 35.8 MT, Tare 11.2 MT. Automated net weight calculated: 24.6 MT (0.6 MT excess).", tbl_cell)],
        [Paragraph("5", tbl_cell_bold), Paragraph("Dispatched Exit", tbl_cell), Paragraph("Truck crosses outbound geofence. Completed rounds increments to 1. Trip status changes to IN_TRANSIT.", tbl_cell)],
        [Paragraph("6", tbl_cell_bold), Paragraph("Corridor Monitoring", tbl_cell), Paragraph("Truck follows NH-48. Leaflet draws solid emerald track over dashed corridor; speed logged at 42 km/h.", tbl_cell)],
        [Paragraph("7", tbl_cell_bold), Paragraph("Checkpoint Scan", tbl_cell), Paragraph("Squad at Kotputli scans driver's QR code on tablet. Screen displays green 'AUTHENTIC PASS' confirmation.", tbl_cell)],
        [Paragraph("8", tbl_cell_bold), Paragraph("Plant Delivery", tbl_cell), Paragraph("Truck reaches Bhiwadi consignee. Pass marked COMPLETED; net 24.6 MT deducted from quarry daily dispatch quota.", tbl_cell)]
    ]
    journey_table = Table(journey_steps, colWidths=[35, 140, 335])
    journey_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(journey_table)

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 30 — ILLEGAL &amp; SUSPICIOUS CASE STUDIES (6 SCENARIOS)", h1_style))
    story.append(make_section_divider())

    cases_data = [
        [Paragraph("<b>Scenario &amp; Modus Operandi</b>", tbl_header), Paragraph("<b>System Detection Rule</b>", tbl_header), Paragraph("<b>Risk Elev.</b>", tbl_header), Paragraph("<b>Squad Enforcement Protocol</b>", tbl_header)],
        [Paragraph("<b>Case 1: Severe Overloading</b><br/>Permit for 24 MT; truck carries 35 MT.", tbl_cell), Paragraph("OVERWEIGHT_DISPATCH<br/>Excess: +11.0 MT", tbl_cell), Paragraph("+30 Pts<br/>(Critical)", tbl_cell), Paragraph("Outbound gate stops vehicle; excess mineral offloaded; fine assessed under Motor Vehicles Act.", tbl_cell)],
        [Paragraph("<b>Case 2: Night-Time Signal Blackout</b><br/>Driver disconnects GPS near riverbed bypass.", tbl_cell), Paragraph("GPS_BLACKOUT<br/>Duration: &gt;15 min", tbl_cell), Paragraph("+20 Pts<br/>(High)", tbl_cell), Paragraph("Flying squad dispatched to last known coordinates; vehicle impounded at next checkpoint.", tbl_cell)],
        [Paragraph("<b>Case 3: Unapproved Route Diversion</b><br/>Truck departs NH-48 into unpermitted rural road.", tbl_cell), Paragraph("ROUTE_DEVIATION<br/>Distance: 2.4 km departure", tbl_cell), Paragraph("+20 Pts<br/>(High)", tbl_cell), Paragraph("GIS visualizer highlights departure; checkpoint squad intercepts vehicle before illegal dumping.", tbl_cell)],
        [Paragraph("<b>Case 4: Pass Recycling / Reuse</b><br/>Truck attempts second trip on consumed permit.", tbl_cell), Paragraph("PERMIT_REUSE<br/>Permit already completed", tbl_cell), Paragraph("+35 Pts<br/>(Critical)", tbl_cell), Paragraph("Gate automatically rejects entry; permit conflict alert emitted; operator flagged for investigation.", tbl_cell)],
        [Paragraph("<b>Case 5: Excessive Round Frequency</b><br/>Truck completes 5th trip on 4-round quota.", tbl_cell), Paragraph("EXCESSIVE_TRIP_FREQUENCY<br/>Rounds: 5 / 4", tbl_cell), Paragraph("+25 Pts<br/>(High)", tbl_cell), Paragraph("Permit issuance blocked; vehicle flagged on Admin and Officer rosters; shift audited.", tbl_cell)],
        [Paragraph("<b>Case 6: Pithead Mass-Balance Mismatch</b><br/>Quarry reports 200 MT blasting but dispatches 500 MT.", tbl_cell), Paragraph("PRODUCTION_MISMATCH<br/>Delta: 300 MT unrecorded", tbl_cell), Paragraph("+25 Pts<br/>(High)", tbl_cell), Paragraph("Mine audit ordered; leasehold dispatch halted; physical laser stockpile survey initiated.", tbl_cell)]
    ]
    cases_table = Table(cases_data, colWidths=[140, 120, 65, 185])
    cases_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(cases_table)

    story.append(PageBreak())

    # =========================================================================
    # SECTION 31, 32 & 33: PLAYBOOKS, TRIAGE & DEMO BOUNDARIES
    # =========================================================================
    story.append(Paragraph("SECTION 31 — DAILY OPERATIONAL PLAYBOOKS", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph("<b>ADMINISTRATOR — DAILY WORKFLOW CHECKLIST:</b>", h2_style))
    story.append(Paragraph("1. <b>Morning Stock Review:</b> Check Admin Command Center for any <i>PRODUCTION-DISPATCH MISMATCH</i> alerts.<br/>"
                           "2. <b>State Dispatch Allocation:</b> Review statewide planned vs. actual dispatch tonnage against annual environmental limits.<br/>"
                           "3. <b>Review High-Risk Fleets:</b> Inspect Top Material Movement table to spot repeat vehicle overloaders.<br/>"
                           "4. <b>Audit Manual Overrides:</b> Review any scale weight adjustments submitted during the previous 24 hours.<br/>"
                           "5. <b>Sign Off Investigations:</b> Review and approve final decisions and penalties in open investigation cases.", body_style))

    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>ENFORCEMENT OFFICER — DAILY SURVEILLANCE PLAYBOOK:</b>", h2_style))
    story.append(Paragraph("1. <b>Log In &amp; Review Alerts Center:</b> Filter for CRITICAL alerts and sort by timestamp.<br/>"
                           "2. <b>Inspect High-Risk Interception Queue:</b> Open top suspicious vehicle (e.g. HR26AB1234).<br/>"
                           "3. <b>Check Live Map Polyline:</b> Verify if current location departs from the dashed authorized corridor.<br/>"
                           "4. <b>Conduct Checkpoint QR Scan:</b> Scan physical passes of intercepted trucks using `/verify-qr`.<br/>"
                           "5. <b>Generate Evidence Dossier:</b> Download court-ready PDF dossier to initiate statutory impoundment.", body_style))

    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>LEASEHOLD OPERATOR — PITHEAD DISPATCH PLAYBOOK:</b>", h2_style))
    story.append(Paragraph("1. <b>Review Opening Stock Balance:</b> Ensure physical quarry extraction matches system opening stock.<br/>"
                           "2. <b>Log Daily Blasting Production:</b> Enter daily extraction quantity in the Stock console.<br/>"
                           "3. <b>Verify Truck Round Quota:</b> Before loading, check that vehicle has remaining rounds today.<br/>"
                           "4. <b>Automated Scale Weighment:</b> Ensure truck passes over weighbridge; verify Gross and Tare.<br/>"
                           "5. <b>Outbound Dispatch:</b> Confirm net weight is compliant before authorizing gate exit.", body_style))

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 32 — 'WHAT SHOULD I CHECK FIRST?' INCIDENT RESPONSE", h1_style))
    story.append(make_section_divider())

    triage_data = [
        [Paragraph("<b>User Role</b>", tbl_header), Paragraph("<b>Critical Alert / Incident Trigger</b>", tbl_header), Paragraph("<b>Immediate 3-Step Action Protocol</b>", tbl_header)],
        [Paragraph("<b>Officer</b>", tbl_cell_bold), Paragraph("CRITICAL Alert: Route Corridor Deviation", tbl_cell), Paragraph("1. Click 'Track Truck' on Officer Dashboard.<br/>2. Note divergence coordinates and distance.<br/>3. Radio nearest border checkpoint squad to intercept.", tbl_cell)],
        [Paragraph("<b>Officer</b>", tbl_cell_bold), Paragraph("HIGH Alert: GPS Signal Blackout", tbl_cell), Paragraph("1. Check last recorded telemetry timestamp.<br/>2. Inspect if blackout occurred near unapproved riverbed.<br/>3. Dispatch flying squad to last recorded GPS point.", tbl_cell)],
        [Paragraph("<b>Operator</b>", tbl_cell_bold), Paragraph("Permit Quota Reached (Blocked)", tbl_cell), Paragraph("1. Verify driver completed rounds count (e.g. 4/4).<br/>2. Do not attempt manual bypass.<br/>3. Schedule vehicle for next day's morning shift.", tbl_cell)],
        [Paragraph("<b>Admin</b>", tbl_cell_bold), Paragraph("Production-Dispatch Mismatch", tbl_cell), Paragraph("1. Click alert banner to open quarry ledger.<br/>2. Compare opening stock + production against dispatches.<br/>3. Dispatch state mining surveyor for physical stockpile audit.", tbl_cell)]
    ]
    triage_table = Table(triage_data, colWidths=[75, 175, 260])
    triage_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(triage_table)

    story.append(Spacer(1, 6))
    story.append(Paragraph("SECTION 33 — REALISTIC DEMO &amp; SIMULATION BOUNDARIES", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph(
        "For Hackathon presentations and administrative demonstrations, SmartMineGuard operates as a fully functional "
        "software prototype. To maintain complete transparency, the following technical boundaries apply:", body_style
    ))

    story.append(Paragraph("• <b>Synthetic GPS Simulator:</b> Live coordinates are generated by an authentic background movement simulator operating within strict Indian geographical borders (Rajasthan / Haryana / NCR). In actual deployment, this connects directly to AIS-140 standard GPS transponders via HTTP/MQTT telemetry streams.<br/>"
                           "• <b>Automated Scale Simulation:</b> Weighbridge gross and tare values are simulated in the demo database. In production, this integrates with RS-232 serial interfaces or IP scale indicators at pithead checkpoints.<br/>"
                           "• <b>Standalone Database:</b> Operates on a hardened SQLite/PostgreSQL relational store without requiring live integration with external national portals (e.g. VAHAN or Sarathi).", body_style))

    story.append(PageBreak())

    # =========================================================================
    # SECTION 34: MASTER QUICK REFERENCE TABLES
    # =========================================================================
    story.append(Paragraph("SECTION 34 — MASTER QUICK REFERENCE DIRECTORY", h1_style))
    story.append(make_section_divider())

    story.append(Paragraph("<b>A. Complete Screen Directory:</b>", h2_style))

    screens_data = [
        [Paragraph("<b>Page / View</b>", tbl_header), Paragraph("<b>Route URL</b>", tbl_header), Paragraph("<b>Primary User</b>", tbl_header), Paragraph("<b>Core Operational Action</b>", tbl_header)],
        [Paragraph("Public Portal", tbl_cell_bold), Paragraph("/", tbl_cell), Paragraph("Public / Transporter", tbl_cell), Paragraph("Verify e-Rawaana, vehicle, and ISTP legitimacy.", tbl_cell)],
        [Paragraph("Officer Sign In", tbl_cell_bold), Paragraph("/login", tbl_cell), Paragraph("All Users", tbl_cell), Paragraph("Secure departmental authentication.", tbl_cell)],
        [Paragraph("Admin Dashboard", tbl_cell_bold), Paragraph("/dashboard", tbl_cell), Paragraph("Administrator", tbl_cell), Paragraph("State dispatch control and mass-balance reconciliation.", tbl_cell)],
        [Paragraph("Officer Dashboard", tbl_cell_bold), Paragraph("/dashboard", tbl_cell), Paragraph("Officer", tbl_cell), Paragraph("High-risk queue triage and dossier generation.", tbl_cell)],
        [Paragraph("Operator Dashboard", tbl_cell_bold), Paragraph("/dashboard", tbl_cell), Paragraph("Operator", tbl_cell), Paragraph("Pithead stock balance and daily dispatch tracking.", tbl_cell)],
        [Paragraph("Live GIS Map", tbl_cell_bold), Paragraph("/map", tbl_cell), Paragraph("Officer, Admin", tbl_cell), Paragraph("Real-time vehicle tracking and route reconstruction.", tbl_cell)],
        [Paragraph("Trucks Fleet", tbl_cell_bold), Paragraph("/trucks", tbl_cell), Paragraph("All Users", tbl_cell), Paragraph("Vehicle fleet roster and cumulative payload tracking.", tbl_cell)],
        [Paragraph("Truck Detail Inspector", tbl_cell_bold), Paragraph("/trucks/<id>", tbl_cell), Paragraph("All Users", tbl_cell), Paragraph("Round quota cards, timeline, and multi-period audits.", tbl_cell)],
        [Paragraph("e-Rawaana Passes", tbl_cell_bold), Paragraph("/permits", tbl_cell), Paragraph("All Users", tbl_cell), Paragraph("Transit pass ledger and cryptographic QR viewing.", tbl_cell)],
        [Paragraph("Transit Trips", tbl_cell_bold), Paragraph("/trips", tbl_cell), Paragraph("All Users", tbl_cell), Paragraph("Trip ledger with round numbering and timeline links.", tbl_cell)],
        [Paragraph("Alerts Center", tbl_cell_bold), Paragraph("/alerts", tbl_cell), Paragraph("Officer, Admin", tbl_cell), Paragraph("Triage and resolve deterministic rule violations.", tbl_cell)],
        [Paragraph("Investigations", tbl_cell_bold), Paragraph("/investigations", tbl_cell), Paragraph("Officer, Admin", tbl_cell), Paragraph("Formal case records, officer notes, penalty collection.", tbl_cell)],
        [Paragraph("QR Verification", tbl_cell_bold), Paragraph("/verify-qr", tbl_cell), Paragraph("Officer", tbl_cell), Paragraph("Mobile scanner for roadside physical inspections.", tbl_cell)],
        [Paragraph("Analytics", tbl_cell_bold), Paragraph("/analytics", tbl_cell), Paragraph("Admin, Officer", tbl_cell), Paragraph("Volume distribution, compliance, and risk trends.", tbl_cell)],
        [Paragraph("Reports & Dossiers", tbl_cell_bold), Paragraph("/reports", tbl_cell), Paragraph("Officer, Admin", tbl_cell), Paragraph("Printable legal PDF investigation packages.", tbl_cell)],
        [Paragraph("Master Data Console", tbl_cell_bold), Paragraph("/admin/data", tbl_cell), Paragraph("Admin, Operator", tbl_cell), Paragraph("CRUD consoles for Mines, Trucks, Drivers, Scales.", tbl_cell)],
        [Paragraph("User Management", tbl_cell_bold), Paragraph("/admin/users", tbl_cell), Paragraph("Administrator", tbl_cell), Paragraph("Managing departmental users, badges, and roles.", tbl_cell)]
    ]
    screens_table = Table(screens_data, colWidths=[105, 95, 100, 210])
    screens_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_primary),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]))
    story.append(screens_table)

    story.append(Spacer(1, 10))
    story.append(Paragraph("<b>B. Complete Vehicle Lifecycle Flow:</b>", h2_style))
    story.append(Paragraph(
        "$$\\text{Truck Registration} \\longrightarrow \\text{e-Rawaana Issuance} \\longrightarrow \\text{GPS Mine Entry} \\longrightarrow "
        "\\text{Permit Auto-Match} \\longrightarrow \\text{Pit Loading} \\longrightarrow \\text{Automated Weighment} \\longrightarrow "
        "\\text{Overload Check} \\longrightarrow \\text{Outbound Mine Exit} \\longrightarrow \\text{Round Incremented} \\longrightarrow "
        "\\text{Corridor Monitoring} \\longrightarrow \\text{Checkpoint Scan} \\longrightarrow \\text{Consignee Delivery} \\longrightarrow "
        "\\text{Trip Reconciliation} \\longrightarrow \\text{Risk Audit} \\longrightarrow \\text{Alert / Dossier If Violated}$$",
        ParagraphStyle("LifeCycleFlow", fontName="Helvetica-Bold", fontSize=8, leading=12, textColor=c_primary, alignment=1)
    ))

    story.append(Spacer(1, 10))
    story.append(make_callout(
        "This official user manual concludes the complete feature, metric, screen, and workflow specification of the "
        "SmartMineGuard Mineral Transport Intelligence Platform. All documented capabilities reflect the active, "
        "functional codebase without artificial intelligence claims or sensitive credential leaks.",
        title="END OF FORMAL MANUAL — DIRECTORATE OF MINES & GEOLOGY",
        border_color="#0F3826", bg_color="#ECFDF5", text_color="#065F46"
    ))

    # Build Document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[SUCCESS] Successfully generated User Manual PDF at: {OUTPUT_PDF}")
    print(f"[SUCCESS] File size: {OUTPUT_PDF.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    build_manual_pdf()
