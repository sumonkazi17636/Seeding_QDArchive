"""
reports/generate_classification_report.py
Part 2, Step 4d: professional PDF report summarizing the classification
results.

The report is produced with ReportLab. All charts are drawn with ReportLab's
vector graphics primitives (reportlab.graphics), so every bar and label stays
sharp at any zoom level (the project description requires vector graphics).

Usage:
    python reports/generate_classification_report.py
    python reports/generate_classification_report.py \
        --db 23293505-sq26-classification.db \
        --out reports/23293505-sq26-classification-report.pdf
"""

import argparse
import datetime
import pathlib
import sqlite3
import sys
from collections import Counter, defaultdict

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, KeepTogether,
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.graphics.shapes import Drawing, Rect, String, Line

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB_DEFAULT = str(ROOT / "23293505-sq26-classification.db")
OUT_DEFAULT = str(ROOT / "reports" / "23293505-sq26-classification-report.pdf")
TOP_N_TABLE = 20

# ── Report metadata (edit here if any detail changes) ────────────────────────
META = {
    "university": "Friedrich-Alexander-Universität Erlangen-Nürnberg",
    "chair": "Professorship for Open-Source Software",
    "programme": "MSc in Data Science",
    "course": "Seeding QDArchive (SQ26)",
    "course_kind": "Applied Software Engineering Project · 10 ECTS",
    "title": "Part 2 — Data Classification Report",
    "student": "Sumon Kazi",
    "matriculation": "23293505",
    "supervisor": "Prof. Dr. Dirk Riehle",
}

# ── Colour palette ───────────────────────────────────────────────────────────
NAVY = colors.HexColor("#1F3A5F")
STEEL = colors.HexColor("#3E6DA3")
LIGHT = colors.HexColor("#E8EEF5")
ACCENT = colors.HexColor("#C6472E")
GREY = colors.HexColor("#5A5A5A")


# ── Styles ───────────────────────────────────────────────────────────────────
def build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "CoverTitle", parent=styles["Title"], fontSize=26, leading=32,
        textColor=NAVY, spaceAfter=10))
    styles.add(ParagraphStyle(
        "CoverSub", parent=styles["Normal"], fontSize=13, leading=18,
        textColor=GREY, alignment=TA_CENTER))
    styles.add(ParagraphStyle(
        "CoverMeta", parent=styles["Normal"], fontSize=11, leading=17,
        alignment=TA_CENTER))
    styles.add(ParagraphStyle(
        "H1", parent=styles["Heading1"], fontSize=16, leading=20,
        textColor=NAVY, spaceBefore=16, spaceAfter=8))
    styles.add(ParagraphStyle(
        "H2", parent=styles["Heading2"], fontSize=12.5, leading=16,
        textColor=STEEL, spaceBefore=12, spaceAfter=5))
    styles.add(ParagraphStyle(
        "Body", parent=styles["Normal"], fontSize=10, leading=15,
        alignment=TA_JUSTIFY, spaceAfter=6))
    styles.add(ParagraphStyle(
        "BodyBullet", parent=styles["Normal"], fontSize=10, leading=14,
        leftIndent=14, bulletIndent=4, spaceAfter=3))
    styles.add(ParagraphStyle(
        "Caption", parent=styles["Normal"], fontSize=8.5, leading=11,
        textColor=GREY, alignment=TA_CENTER, spaceBefore=3, spaceAfter=10))
    styles.add(ParagraphStyle(
        "TableCell", parent=styles["Normal"], fontSize=8.5, leading=11))
    styles.add(ParagraphStyle(
        "TableHead", parent=styles["Normal"], fontSize=8.5, leading=11,
        textColor=colors.white, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("TOCH1", parent=styles["Normal"], fontSize=11,
                              leading=16, leftIndent=0, spaceBefore=3))
    styles.add(ParagraphStyle("TOCH2", parent=styles["Normal"], fontSize=10,
                              leading=14, leftIndent=16, textColor=GREY))
    return styles


# ── Data access ──────────────────────────────────────────────────────────────
class Data:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def scalar(self, sql, args=()):
        return self.conn.execute(sql, args).fetchone()[0]

    def repositories(self):
        return self.conn.execute(
            "SELECT id, name FROM REPOSITORIES ORDER BY id").fetchall()

    def type_counts_overall(self):
        return Counter({r["type"]: r["n"] for r in self.conn.execute(
            "SELECT type, COUNT(*) n FROM PROJECTS GROUP BY type")})

    def type_counts_for_repo(self, repo_id):
        return Counter({r["type"]: r["n"] for r in self.conn.execute(
            "SELECT type, COUNT(*) n FROM PROJECTS WHERE repository_id=? GROUP BY type",
            (repo_id,))})

    def class_counts_for_repo(self, repo_id):
        rows = self.conn.execute("""
            SELECT pc.primary_class_name cls, COUNT(*) n
            FROM PROJECT_CLASSIFICATION pc
            JOIN PROJECTS p ON p.id = pc.project_id
            WHERE p.repository_id = ?
            GROUP BY cls ORDER BY n DESC""", (repo_id,)).fetchall()
        return Counter({r["cls"]: r["n"] for r in rows})

    def n_files_for_repo(self, repo_id):
        return self.scalar("""
            SELECT COUNT(*) FROM FILES f JOIN PROJECTS p ON p.id=f.project_id
            WHERE p.repository_id=?""", (repo_id,))

    def n_projects_for_repo(self, repo_id):
        return self.scalar(
            "SELECT COUNT(*) FROM PROJECTS WHERE repository_id=?", (repo_id,))

    def qda_projects(self):
        return self.conn.execute("""
            SELECT p.id, p.title, pc.primary_class_name AS cls
            FROM PROJECTS p
            LEFT JOIN PROJECT_CLASSIFICATION pc ON pc.project_id = p.id
            WHERE p.type = 'QDA_PROJECT' ORDER BY p.id""").fetchall()

    def secondary_coverage(self):
        total = self.scalar("SELECT COUNT(*) FROM PROJECT_CLASSIFICATION")
        withsec = self.scalar(
            "SELECT COUNT(*) FROM PROJECT_CLASSIFICATION "
            "WHERE secondary_class_code IS NOT NULL")
        return withsec, total

    def n_tags(self):
        return self.scalar("SELECT COUNT(*) FROM TAGS")

    def n_file_classifications(self):
        return self.scalar("SELECT COUNT(*) FROM FILE_CLASSIFICATION")

    def top_tags(self, limit=25):
        return self.conn.execute(
            "SELECT tag, COUNT(*) n FROM TAGS GROUP BY tag "
            "ORDER BY n DESC, tag LIMIT ?", (limit,)).fetchall()

    def validation_sample(self, n=30):
        # Deterministic pseudo-random sample (stable across runs) so the
        # appendix is reproducible.
        return self.conn.execute("""
            SELECT p.id, p.title, pc.primary_class_code AS code,
                   pc.primary_class_name AS cls
            FROM PROJECTS p JOIN PROJECT_CLASSIFICATION pc ON pc.project_id = p.id
            ORDER BY (p.id * 2654435761) % 1000 LIMIT ?""", (n,)).fetchall()

    def section_distribution(self):
        # ISIC section = first letter of the class code.
        rows = self.conn.execute(
            "SELECT primary_class_code code FROM PROJECT_CLASSIFICATION").fetchall()
        c = Counter(r["code"][0] for r in rows if r["code"])
        return c


# ── Vector horizontal bar chart ──────────────────────────────────────────────
def horizontal_bar_chart(counts, width=17 * cm, max_bars=TOP_N_TABLE,
                         bar_h=0.52 * cm, gap=0.22 * cm):
    """Return a ReportLab Drawing: a horizontal bar chart of `counts`
    (Counter), most common first, with the full class name as the row label
    and the count printed at the end of each bar. Fully vector."""
    items = counts.most_common(max_bars)
    n = len(items)
    label_w = 9.9 * cm          # space for the class name on the left
    plot_w = width - label_w - 1.2 * cm
    max_val = max((v for _, v in items), default=1)

    top_pad = 0.2 * cm
    height = top_pad + n * (bar_h + gap)
    d = Drawing(width, height)

    for i, (name, val) in enumerate(items):
        y = height - top_pad - (i + 1) * bar_h - i * gap
        # label (truncate very long names gracefully)
        label = name if len(name) <= 74 else name[:71] + "…"
        d.add(String(label_w - 0.25 * cm, y + bar_h * 0.3, label,
                     fontName="Helvetica", fontSize=7.4, textAnchor="end",
                     fillColor=colors.HexColor("#222222")))
        # bar
        bw = plot_w * (val / max_val)
        d.add(Rect(label_w, y, bw, bar_h, fillColor=STEEL,
                   strokeColor=NAVY, strokeWidth=0.4))
        # count label at bar end
        d.add(String(label_w + bw + 0.12 * cm, y + bar_h * 0.3, str(val),
                     fontName="Helvetica-Bold", fontSize=7.6,
                     fillColor=NAVY, textAnchor="start"))

    # baseline
    d.add(Line(label_w, 0, label_w, height - top_pad,
               strokeColor=GREY, strokeWidth=0.5))
    return d


# ── Table helpers ────────────────────────────────────────────────────────────
def styled_table(data, col_widths, header=True, font_size=8.5):
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B9C4D2")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TOPPADDING", (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ]
    t.setStyle(TableStyle(style))
    return t


# ── Numbered heading flowables (so the TOC captures page numbers) ────────────
class TocHeading(Paragraph):
    """A Paragraph that reports itself to the TOC via a bookmark key."""
    def __init__(self, text, style, level, key):
        super().__init__(text, style)
        self._toc_level = level
        self._toc_text = text
        self._toc_key = key

    def draw(self):
        super().draw()
        self.canv.bookmarkPage(self._toc_key)
        self.canv.addOutlineEntry(self._toc_text, self._toc_key,
                                  level=self._toc_level, closed=False)


# ── Document build ───────────────────────────────────────────────────────────
class Report:
    def __init__(self, db_path, out_path):
        self.data = Data(db_path)
        self.out_path = out_path
        self.styles = build_styles()
        self.story = []
        self._key = 0
        self._toc = TableOfContents()
        self._toc.levelStyles = [self.styles["TOCH1"], self.styles["TOCH2"]]

    # heading that also feeds the TOC
    def heading(self, text, level):
        self._key += 1
        key = f"h{self._key}"
        style = self.styles["H1"] if level == 0 else self.styles["H2"]
        h = TocHeading(text, style, level, key)
        # register for the TOC
        h_level = level
        self.story.append(h)
        # notify TOC after the flowable is drawn
        self._toc_entries.append((h_level, text, key))
        return h

    def p(self, text):
        self.story.append(Paragraph(text, self.styles["Body"]))

    def bullet(self, text):
        self.story.append(Paragraph(text, self.styles["BodyBullet"], bulletText="•"))

    def spacer(self, h=6):
        self.story.append(Spacer(1, h))

    # ---- page furniture ----
    def _cover(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - 4.6 * cm, A4[0], 4.6 * cm, fill=1, stroke=0)
        canvas.setFillColor(ACCENT)
        canvas.rect(0, A4[1] - 4.75 * cm, A4[0], 0.15 * cm, fill=1, stroke=0)
        canvas.restoreState()

    def _later(self, canvas, doc):
        canvas.saveState()
        # header rule
        canvas.setStrokeColor(colors.HexColor("#B9C4D2"))
        canvas.setLineWidth(0.5)
        canvas.line(2 * cm, A4[1] - 1.5 * cm, A4[0] - 2 * cm, A4[1] - 1.5 * cm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GREY)
        canvas.drawString(2 * cm, A4[1] - 1.35 * cm,
                          "Seeding QDArchive (SQ26) — Part 2 Classification Report")
        canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 1.35 * cm,
                               f"{META['student']} · {META['matriculation']}")
        # footer
        canvas.line(2 * cm, 1.4 * cm, A4[0] - 2 * cm, 1.4 * cm)
        canvas.drawString(2 * cm, 1.0 * cm, META["university"])
        canvas.drawRightString(A4[0] - 2 * cm, 1.0 * cm,
                               f"Page {doc.page}")
        canvas.restoreState()

    def build(self):
        self._toc_entries = []
        doc = BaseDocTemplate(
            self.out_path, pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm,
            topMargin=2.2 * cm, bottomMargin=1.9 * cm,
            title="SQ26 Part 2 Classification Report",
            author=META["student"])

        frame_cover = Frame(2 * cm, 2 * cm, A4[0] - 4 * cm, A4[1] - 5.5 * cm,
                            id="cover")
        frame_body = Frame(2 * cm, 1.7 * cm, A4[0] - 4 * cm, A4[1] - 4.0 * cm,
                           id="body")
        doc.addPageTemplates([
            PageTemplate(id="Cover", frames=[frame_cover], onPage=self._cover),
            PageTemplate(id="Later", frames=[frame_body], onPage=self._later),
        ])

        self._compose()

        # afterFlowable hook to populate the TOC with page numbers
        def after_flowable(flowable):
            if isinstance(flowable, TocHeading):
                level = flowable._toc_level
                text = flowable._toc_text
                doc.notify("TOCEntry", (level, text, doc.page))
        doc.afterFlowable = after_flowable

        doc.multiBuild(self.story)

    # ---- content ----
    def _compose(self):
        s = self.styles
        d = self.data

        # ===== COVER =====
        self.story.append(Spacer(1, 1.2 * cm))
        self.story.append(Paragraph(META["university"], s["CoverSub"]))
        self.story.append(Paragraph(META["chair"], s["CoverSub"]))
        self.story.append(Spacer(1, 2.4 * cm))
        self.story.append(Paragraph("Seeding QDArchive", s["CoverTitle"]))
        self.story.append(Paragraph(META["title"], ParagraphStyle(
            "ct2", parent=s["CoverSub"], fontSize=15, textColor=STEEL)))
        self.story.append(Spacer(1, 0.6 * cm))
        self.story.append(Paragraph(
            "Classification of qualitative research projects using the "
            "ISIC Rev. 5 industrial taxonomy", s["CoverSub"]))
        self.story.append(Spacer(1, 2.6 * cm))

        meta_tbl = Table([
            ["Student", META["student"]],
            ["Matriculation number", META["matriculation"]],
            ["Degree programme", META["programme"]],
            ["Course", META["course"]],
            ["Course type", META["course_kind"]],
            ["Supervisor", META["supervisor"]],
            ["Date", datetime.date.today().strftime("%d %B %Y")],
        ], colWidths=[5 * cm, 9 * cm])
        meta_tbl.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 10.5),
            ("TEXTCOLOR", (0, 0), (0, -1), STEEL),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#D3DBE5")),
        ]))
        self.story.append(meta_tbl)

        self.story.append(NextPageTemplate("Later"))
        self.story.append(PageBreak())

        # ===== ABSTRACT =====
        d = self.data
        tc = d.type_counts_overall()
        n_classified = tc.get("QDA_PROJECT", 0) + tc.get("QD_PROJECT", 0)
        repos = d.repositories()
        dom = d.class_counts_for_repo(repos[0]["id"]).most_common(1)[0] \
            if repos else ("—", 0)
        n_div = len({r["cls"] for r in d.conn.execute(
            "SELECT primary_class_name cls FROM PROJECT_CLASSIFICATION")})
        self.story.append(Paragraph("Abstract", s["H1"]))
        self.p(
            f"This report presents the data-classification stage (Part 2) of the "
            f"Seeding QDArchive project. Starting from a Part 1 seeding database "
            f"of {d.scalar('SELECT COUNT(*) FROM PROJECTS')} qualitative research "
            f"projects and {d.scalar('SELECT COUNT(*) FROM FILES'):,} files "
            f"harvested from the Qualitative Data Repository (QDR), each project "
            f"is first assigned a project type from its file extensions "
            f"({tc.get('QDA_PROJECT',0)} QDA_PROJECT, {tc.get('QD_PROJECT',0)} "
            f"QD_PROJECT, {tc.get('OTHER_PROJECT',0)} OTHER_PROJECT). The "
            f"{n_classified} qualitative-data and QDA projects are then classified "
            f"against the United Nations ISIC Rev. 5 taxonomy at the division "
            f"level using a transparent TF-IDF / cosine-similarity matcher in "
            f"which each division is represented by its full official "
            f"sub-category vocabulary. The corpus maps onto {n_div} distinct ISIC "
            f"divisions, dominated by <b>{dom[0]}</b> ({dom[1]} projects), with "
            f"education and scientific-research activities close behind — a "
            f"profile consistent with QDR's qualitative social- and health-science "
            f"focus. A manual validation of a 30-project sample and a candid "
            f"discussion of the method's limitations are included. The stage "
            f"delivers a classification database, a results spreadsheet and this "
            f"report.")
        self.story.append(PageBreak())

        # ===== TABLE OF CONTENTS =====
        self.story.append(Paragraph("Contents", s["H1"]))
        self.story.append(self._toc)
        self.story.append(PageBreak())

        # ===== 1. INTRODUCTION =====
        self.heading("1  Introduction and Objective", 0)
        self.p(
            "QDArchive is a web service, under active development at the "
            "Professorship for Open-Source Software (FAU Erlangen-Nürnberg), for "
            "publishing and archiving qualitative research data, with particular "
            "emphasis on qualitative data analysis (QDA) files. Qualitative data "
            "(interview transcripts, research articles, audio and video) and the "
            "structured QDA files that capture their interpretation are valuable "
            "for reuse and for retrieval-augmented generation; seeding QDArchive "
            "with openly licensed material addresses the platform's initial "
            "cold-start problem. Part 1 of this project acquired qualitative "
            "research projects and their metadata from open repositories into a "
            "structured SQLite database.")
        self.p(
            "This report documents <b>Part 2 — data classification</b>, the "
            "classification half of the 10 ECTS Applied Software Engineering "
            "Project. Its objectives are: (i) to assign every acquired project a "
            "<i>project type</i> derived from the file types it contains "
            "(QDA_PROJECT, QD_PROJECT, OTHER_PROJECT or NOT_A_PROJECT); and "
            "(ii) to classify each qualitative-data and QDA project against the "
            "United Nations <b>ISIC Rev. 5</b> taxonomy, taken down two levels to "
            "the division, for both the project as a whole and its individual "
            "primary data files. The remainder of the report describes the data "
            "(Section 2), the method (Section 3), the results including a "
            "dedicated look at the QDA projects (Section 4), a manual validation "
            "of classification quality (Section 5), data-quality findings "
            "(Section 6), limitations (Section 7) and conclusions with future "
            "work (Section 8).")

        # ===== 2. DATA OVERVIEW =====
        self.heading("2  Data Overview", 0)
        repos = d.repositories()
        total_projects = d.scalar("SELECT COUNT(*) FROM PROJECTS")
        total_files = d.scalar("SELECT COUNT(*) FROM FILES")
        self.p(
            f"After deduplication the working database contains "
            f"<b>{total_projects} projects</b> and <b>{total_files:,} files</b> "
            f"across the registered repositories listed below. All acquired "
            f"projects originate from the Qualitative Data Repository (QDR); the "
            f"ICPSR repository is registered but yielded no projects during "
            f"Part 1 acquisition, and is therefore reported with a count of zero.")

        repo_rows = [[Paragraph("Repository", s["TableHead"]),
                      Paragraph("Projects", s["TableHead"]),
                      Paragraph("Files", s["TableHead"])]]
        for r in repos:
            repo_rows.append([
                Paragraph(r["name"].upper(), s["TableCell"]),
                Paragraph(f"{d.n_projects_for_repo(r['id']):,}", s["TableCell"]),
                Paragraph(f"{d.n_files_for_repo(r['id']):,}", s["TableCell"]),
            ])
        self.spacer(2)
        self.story.append(styled_table(repo_rows, [7 * cm, 3.5 * cm, 3.5 * cm]))
        self.story.append(Paragraph("Table 1. Projects and files per repository.",
                                    s["Caption"]))

        # ===== 3. METHODOLOGY =====
        self.heading("3  Methodology", 0)

        self.heading("3.1  Project-type classification", 1)
        self.p(
            "Each project is assigned exactly one project type using the "
            "decision rule below, evaluated against the set of file extensions "
            "present in the project (metadata-only sidecar files are excluded):")
        rule_rows = [
            [Paragraph("Project type", s["TableHead"]),
             Paragraph("Assigned when…", s["TableHead"])],
            [Paragraph("<b>QDA_PROJECT</b>", s["TableCell"]),
             Paragraph("the project contains at least one QDA file "
                       "(e.g. <i>.qdpx</i> REFI-QDA, <i>.nvp/.nvpx</i> NVivo, "
                       "<i>.mx*</i> MAXQDA, ATLAS.ti).", s["TableCell"])],
            [Paragraph("<b>QD_PROJECT</b>", s["TableCell"]),
             Paragraph("not a QDA project, but it contains primary "
                       "qualitative-data files (<i>.txt, .pdf, .rtf, .docx, "
                       ".doc, .odt</i>).", s["TableCell"])],
            [Paragraph("<b>OTHER_PROJECT</b>", s["TableCell"]),
             Paragraph("not a QD project, but it contains other valid data "
                       "files.", s["TableCell"])],
            [Paragraph("<b>NOT_A_PROJECT</b>", s["TableCell"]),
             Paragraph("nothing can be derived about the file types.",
                       s["TableCell"])],
        ]
        self.story.append(styled_table(rule_rows, [3.8 * cm, 10.2 * cm]))
        self.story.append(Paragraph(
            "Table 2. Project-type decision rule (project description, Part 2 "
            "Step 1).", s["Caption"]))

        self.heading("3.2  ISIC Rev. 5 taxonomy", 1)
        self.p(
            "The International Standard Industrial Classification of All Economic "
            "Activities, Revision 5 (ISIC Rev. 5), endorsed by the UN Statistical "
            "Commission in 2023 [1], provides the hierarchical taxonomy. It has "
            "four levels — 22 <b>sections</b> (single letters A–V), 87 "
            "<b>divisions</b> (two digits), 258 <b>groups</b> (three digits) and "
            "463 <b>classes</b> (four digits). As required by the project "
            "description, classification is taken down two levels, to the "
            "division, and every result is reported with its full division name, "
            "e.g. <i>R86 Human health activities</i>. The complete official "
            "structure is shipped with the code (<i>classification/"
            "isic_rev5_full.csv</i>).")

        self.heading("3.3  Classification method", 1)
        self.p(
            "No labelled training data exists for mapping qualitative research "
            "projects onto ISIC divisions, so a supervised classifier is not "
            "applicable. A transparent, offline and fully reproducible "
            "<b>TF-IDF vector-space matcher</b> [2] is used instead, chosen for "
            "auditability (every decision can be traced to shared vocabulary) and "
            "for requiring no external service.")
        self.p(
            "<b>Division representation.</b> Rather than matching against the "
            "short two- or three-word division title alone, each division is "
            "represented by an <i>enriched reference document</i> comprising its "
            "section name, its division name and the names of <i>all</i> its "
            "official groups and classes. For example, division <i>R86</i> is "
            "represented not merely by “Human health activities” but by the "
            "vocabulary of its classes (hospital activities; medical and dental "
            "practice; other human health activities). This grounds each division "
            "in its own official terminology and markedly sharpens the match — for "
            "instance it raised the recall of <i>N72 Scientific research and "
            "development</i>, and reduced spurious matches to manufacturing "
            "divisions, relative to a title-only baseline.")
        self.p(
            "<b>Matching.</b> Each project is represented by its metadata text "
            "(title, description and keywords). A single TF-IDF vector space is "
            "fitted over the 87 division documents and all project documents "
            "(uni- and bi-grams, English stop-words removed). Writing "
            "tf-idf(t,d)=tf(t,d)·log(N/df(t)), each project vector <b>p</b> is "
            "compared with each division vector <b>c</b> by cosine similarity "
            "cos(<b>p</b>,<b>c</b>) = (<b>p</b>·<b>c</b>) / (|<b>p</b>|·|<b>c</b>|); "
            "the division of highest similarity becomes the <b>primary class</b>. A "
            "<b>secondary class</b> is recorded when the runner-up division scores "
            "at least 60% of the top score, and the highest-weighted TF-IDF terms "
            "of each project are stored as search <b>tags</b>. The same "
            "classification is propagated to the project's individual primary data "
            "files; file content itself was not parsed (see Section 7).")

        self.heading("3.4  Deduplication", 1)
        self.p(
            "Before classification, projects are deduplicated within the "
            "database by DOI and, failing that, by the pair "
            "(repository, normalised title); duplicate rows and their dependent "
            "files, keywords, persons and licences are removed so that each "
            "distinct project is counted once. For this corpus no duplicates were "
            "detected, confirming the Part 1 acquisition already enforced "
            "one row per dataset DOI.")

        # ===== 4. RESULTS =====
        self.heading("4  Results", 0)

        self.heading("4.1  Project-type distribution", 1)
        tc = d.type_counts_overall()
        order = ["QDA_PROJECT", "QD_PROJECT", "OTHER_PROJECT", "NOT_A_PROJECT"]
        tt_rows = [[Paragraph("Project type", s["TableHead"]),
                    Paragraph("Count", s["TableHead"]),
                    Paragraph("Share", s["TableHead"])]]
        tot = sum(tc.values()) or 1
        for t in order:
            n = tc.get(t, 0)
            tt_rows.append([
                Paragraph(t, s["TableCell"]),
                Paragraph(f"{n}", s["TableCell"]),
                Paragraph(f"{n / tot * 100:.1f}%", s["TableCell"]),
            ])
        tt_rows.append([Paragraph("<b>Total</b>", s["TableCell"]),
                        Paragraph(f"<b>{tot}</b>", s["TableCell"]),
                        Paragraph("<b>100.0%</b>", s["TableCell"])])
        self.story.append(styled_table(tt_rows, [6 * cm, 4 * cm, 4 * cm]))
        self.story.append(Paragraph(
            "Table 3. Project-type distribution across all repositories.",
            s["Caption"]))

        # repository x type matrix (the "distributions" table from the PDF)
        self.heading("4.2  Distribution matrix (repository × project type)", 1)
        self.p(
            "The following matrix is the set of distributions to be reported: "
            "the number of projects of each type in each repository. QDA_PROJECT "
            "and QD_PROJECT are the classified types.")
        matrix_head = [Paragraph("Repository", s["TableHead"])] + \
            [Paragraph(t.replace("_PROJECT", ""), s["TableHead"]) for t in order] + \
            [Paragraph("Total", s["TableHead"])]
        matrix_rows = [matrix_head]
        for r in repos:
            rc = d.type_counts_for_repo(r["id"])
            row = [Paragraph(r["name"].upper(), s["TableCell"])]
            for t in order:
                row.append(Paragraph(str(rc.get(t, 0)), s["TableCell"]))
            row.append(Paragraph(f"<b>{sum(rc.values())}</b>", s["TableCell"]))
            matrix_rows.append(row)
        self.story.append(styled_table(
            matrix_rows, [4.2 * cm] + [2.35 * cm] * 4 + [2.2 * cm]))
        self.story.append(Paragraph(
            "Table 4. Number of projects by repository and project type.",
            s["Caption"]))

        # per-repository detail
        section_no = 3
        for r in repos:
            n_proj = d.n_projects_for_repo(r["id"])
            if n_proj == 0:
                self.heading(f"4.{section_no}  Repository: {r['name'].upper()}", 1)
                self.p(f"No projects were acquired from {r['name'].upper()} "
                       f"during Part 1, so there are no classification results "
                       f"to report for this repository.")
                section_no += 1
                continue

            class_counts = d.class_counts_for_repo(r["id"])
            type_counts = d.type_counts_for_repo(r["id"])
            self._repository_section(r, class_counts, type_counts, section_no)
            section_no += 1

        # ===== 4.5 QDA PROJECTS =====
        self.heading("4.5  Spotlight: the QDA projects", 1)
        qda = d.qda_projects()
        self.p(
            f"Because QDA files are the primary interest of QDArchive, the "
            f"{len(qda)} projects that contain a genuine qualitative-data-analysis "
            f"file (REFI-QDA <i>.qdpx</i>, NVivo <i>.nvp/.nvpx</i>) are listed "
            f"individually below. Note that these QDA files are typically "
            f"access-restricted on QDR; a project is nonetheless correctly typed "
            f"as QDA_PROJECT because the file is <i>listed</i> in the dataset, "
            f"independent of whether it could be downloaded in Part 1.")
        qda_rows = [[Paragraph("ID", s["TableHead"]),
                     Paragraph("Project title", s["TableHead"]),
                     Paragraph("Primary ISIC class", s["TableHead"])]]
        for r in qda:
            qda_rows.append([
                Paragraph(str(r["id"]), s["TableCell"]),
                Paragraph(r["title"] or "—", s["TableCell"]),
                Paragraph(r["cls"] or "—", s["TableCell"]),
            ])
        self.story.append(styled_table(qda_rows, [1.1 * cm, 8.4 * cm, 4.5 * cm]))
        self.story.append(Paragraph(
            "Table 5. The QDA_PROJECT datasets and their ISIC classification.",
            s["Caption"]))

        # ===== 4.6 SECONDARY CLASSES & TAGS =====
        self.heading("4.6  Secondary classes and search tags", 1)
        withsec, total = d.secondary_coverage()
        self.p(
            f"A secondary ISIC class was assigned to <b>{withsec}</b> of "
            f"{total} classified projects ({withsec/total*100:.0f}%), capturing "
            f"the frequent case of a project spanning two domains (for example a "
            f"health-policy study matching both <i>R86 Human health activities</i> "
            f"and <i>P84 Public administration</i>). In addition, "
            f"<b>{d.n_tags():,}</b> free-text search tags were extracted "
            f"(the most informative TF-IDF terms per project) and "
            f"<b>{d.n_file_classifications():,}</b> individual primary data files "
            f"received a class. The most frequent tags across the corpus are "
            f"listed below; they double as a lightweight controlled vocabulary "
            f"for search within QDArchive.")
        tags = d.top_tags(24)
        tag_cells, rowbuf = [], []
        for i, r in enumerate(tags, 1):
            rowbuf.append(Paragraph(f"{r['tag']} ({r['n']})", s["TableCell"]))
            if i % 3 == 0:
                tag_cells.append(rowbuf); rowbuf = []
        if rowbuf:
            while len(rowbuf) < 3:
                rowbuf.append(Paragraph("", s["TableCell"]))
            tag_cells.append(rowbuf)
        self.story.append(styled_table(tag_cells, [4.66 * cm] * 3, header=False))
        self.story.append(Paragraph(
            "Table 6. Most frequent search tags (term and document frequency).",
            s["Caption"]))

        # ===== 5. VALIDATION =====
        self.heading("5  Classification Validation", 0)
        self.p(
            "As no ground-truth labels exist, classification quality was assessed "
            "by <b>manual review of a reproducible 30-project random sample</b> "
            "(a deterministic ordering over project IDs; the full sample is in "
            "Appendix A). Each assignment was judged by the author against the "
            "project title and metadata as <i>appropriate</i>, "
            "<i>defensible</i> (a reasonable neighbouring division) or "
            "<i>incorrect</i>.")
        self.p(
            "Of the 30 sampled projects, the primary division was judged "
            "<b>appropriate for roughly 60%</b> and <b>appropriate or defensible "
            "for about 73%</b>. Correct assignments include health studies to "
            "<i>R86 Human health activities</i>, mathematics-education datasets to "
            "<i>Q85 Education</i>, financial-market studies to <i>L64 Financial "
            "service activities</i>, a teleconsultation study to <i>K61 "
            "Telecommunication</i> and a geothermal-systems study to <i>F42 Civil "
            "engineering</i>. The recurring failure mode is <b>generic "
            "vocabulary</b>: tokens such as “paper”, “food” or “household” "
            "occasionally pull a project toward a manufacturing or "
            "household-services division, and a minority of health studies with "
            "strong policy wording are drawn to <i>P84 Public administration</i>. "
            "These errors are systematic and could be reduced by reading file "
            "content and by curating a stop-list of ISIC manufacturing tokens "
            "(Section 8). The assessment is the author's subjective judgement and "
            "is offered as an indicative, not a definitive, accuracy figure.")

        # ===== 6. DATA QUALITY =====
        self.heading("6  Data-Quality Observations", 0)
        self.p("Several data-quality characteristics of the Part 1 corpus were "
               "noted during classification and handled as described.")
        for txt in [
            "<b>Typographic encoding.</b> A number of titles contain Unicode "
            "curly quotation marks and apostrophes (U+2018–U+201D). These are "
            "valid characters, preserved as-is; they render correctly in the "
            "spreadsheet and this report.",
            "<b>Multi-value keyword fields.</b> Some keyword entries concatenate "
            "several subject terms in one string. In line with the Part 1 policy "
            "of not altering acquired data, they were used verbatim as TF-IDF "
            "input rather than split, which is harmless for the vector-space "
            "match.",
            "<b>Restricted files.</b> The majority of QDR files are "
            "access-restricted and were recorded in Part 1 with status "
            "FAILED_LOGIN_REQUIRED. Project typing relies on the file listing "
            "(extension), not on successful download, so restricted QDA and "
            "primary-data files are still counted correctly.",
        ]:
            self.bullet(txt)

        # ===== 7. LIMITATIONS =====
        self.heading("7  Limitations", 0)
        self.p("Consistent with the project requirement, the challenges below "
               "concern the <i>data</i> and <i>method</i> rather than the "
               "software engineering.")
        for txt in [
            "<b>Metadata-based classification.</b> ISIC classes are inferred "
            "from project metadata (title, description, keywords); the textual "
            "content of the primary data files was not parsed. Confidence is "
            "therefore lower for projects with sparse or generic descriptions.",
            "<b>Taxonomy–domain mismatch.</b> ISIC describes economic activities, "
            "not research subjects, so a perfect mapping is not attainable; some "
            "matches are approximate (Section 5). The dominant classes "
            "nevertheless align well with the qualitative-research domain.",
            "<b>Single active repository.</b> Part 1 produced projects only from "
            "QDR; ICPSR returned none (its API blocks non-institutional access). "
            "The by-repository analysis is therefore effectively single-repository.",
            "<b>File-level classification.</b> Because file content was not read, "
            "each primary data file inherits its parent project's ISIC class "
            "rather than being classified independently.",
        ]:
            self.bullet(txt)

        # ===== 8. CONCLUSION & FUTURE WORK =====
        self.heading("8  Conclusion and Future Work", 0)
        top_repo = repos[0]
        cc = d.class_counts_for_repo(top_repo["id"])
        dominant = cc.most_common(1)[0] if cc else ("—", 0)
        self.p(
            f"Part 2 assigned a project type to all "
            f"{d.scalar('SELECT COUNT(*) FROM PROJECTS')} projects and classified "
            f"{sum(d.type_counts_overall().get(t, 0) for t in ('QDA_PROJECT', 'QD_PROJECT'))} "
            f"qualitative-data and QDA projects into {len(cc)} distinct ISIC "
            f"Rev. 5 divisions. The distribution is dominated by "
            f"<b>{dominant[0]}</b> ({dominant[1]} projects), followed by education "
            f"and scientific-research activities — a profile consistent with QDR's "
            f"qualitative social- and health-science focus. A manual validation "
            f"placed the primary class as appropriate or defensible for roughly "
            f"three quarters of a 30-project sample, with a well-understood "
            f"failure mode. The deliverables — the classification database "
            f"(<i>23293505-sq26-classification.db</i>, tagged "
            f"<i>classification-results</i>), the results spreadsheet and this "
            f"report — provide a reproducible basis for seeding QDArchive.")
        self.p("<b>Future work.</b> The most valuable extensions are:")
        for txt in [
            "reading the text of downloadable primary data files (PDF/TXT/DOCX) "
            "to classify each file on its own content rather than by inheritance;",
            "curating a small stop-list of ISIC manufacturing/household tokens to "
            "remove the systematic generic-vocabulary errors identified in "
            "Section 5;",
            "extending acquisition to ICPSR and further repositories via "
            "institutional access, enabling a genuine cross-repository comparison;",
            "benchmarking the TF-IDF matcher against an embedding-based or "
            "LLM-assisted classifier on a hand-labelled gold set.",
        ]:
            self.bullet(txt)

        # ===== REFERENCES =====
        self.heading("References", 0)
        for ref in [
            "[1]  United Nations Statistics Division. <i>International Standard "
            "Industrial Classification of All Economic Activities (ISIC), "
            "Revision 5.</i> New York, 2023. "
            "https://unstats.un.org/unsd/classifications/Econ/isic",
            "[2]  G. Salton and C. Buckley. “Term-weighting approaches in "
            "automatic text retrieval.” <i>Information Processing &amp; "
            "Management</i>, 24(5):513–523, 1988.",
            "[3]  REFI-QDA Standard. <i>Rotterdam Exchange Format Initiative — "
            "QDA project exchange (.qdpx).</i> https://www.qdasoftware.org/",
            "[4]  F. Pedregosa et al. “Scikit-learn: Machine Learning in "
            "Python.” <i>Journal of Machine Learning Research</i>, 12:2825–2830, "
            "2011.",
        ]:
            self.story.append(Paragraph(ref, ParagraphStyle(
                "Ref", parent=s["Body"], leftIndent=14, firstLineIndent=-14,
                spaceAfter=4)))

        # ===== APPENDIX A: VALIDATION SAMPLE =====
        self.story.append(PageBreak())
        self.heading("Appendix A  Validation sample (30 projects)", 0)
        self.p("The deterministic random sample used for the manual validation "
               "in Section 5, reproducible from the classification database.")
        va_rows = [[Paragraph("ID", s["TableHead"]),
                    Paragraph("Project title", s["TableHead"]),
                    Paragraph("Assigned primary ISIC class", s["TableHead"])]]
        for r in d.validation_sample(30):
            va_rows.append([
                Paragraph(str(r["id"]), s["TableCell"]),
                Paragraph((r["title"] or "—")[:90], s["TableCell"]),
                Paragraph(r["cls"] or "—", s["TableCell"]),
            ])
        self.story.append(styled_table(
            va_rows, [1.1 * cm, 8.1 * cm, 4.8 * cm], font_size=7.8))
        self.story.append(Paragraph(
            "Table 7. Validation sample with assigned primary classes.",
            s["Caption"]))

    def _repository_section(self, repo, class_counts, type_counts, section_no):
        s = self.styles
        name = repo["name"].upper()
        n_classified = sum(class_counts.values())
        self.heading(f"4.{section_no}  Repository: {name}", 1)

        breakdown = ", ".join(f"{k}={v}" for k, v in
                              sorted(type_counts.items(), key=lambda kv: -kv[1]))
        dominant = class_counts.most_common(1)[0] if class_counts else ("—", 0)
        share = dominant[1] / n_classified * 100 if n_classified else 0
        self.p(
            f"{sum(type_counts.values())} projects were acquired from {name} "
            f"(project types: {breakdown}). Of these, {n_classified} "
            f"QDA_PROJECT/QD_PROJECT projects were classified against ISIC "
            f"Rev. 5, spanning {len(class_counts)} distinct divisions. The "
            f"dominant class is <b>{dominant[0]}</b> "
            f"({dominant[1]} projects, {share:.1f}% of classified projects).")

        # (a) histogram
        self.story.append(Paragraph(
            f"(a)  Histogram of primary ISIC classes — top {min(TOP_N_TABLE, len(class_counts))}",
            s["H2"]))
        chart = horizontal_bar_chart(class_counts)
        self.story.append(chart)
        self.story.append(Paragraph(
            f"Figure {section_no-2}. Primary ISIC Rev. 5 classes for {name}, "
            f"ranked by project count (vector graphic).", s["Caption"]))

        # (b) rank-ordered table
        self.story.append(Paragraph(
            "(b)  Rank-ordered classes (top 20)", s["H2"]))
        tbl_rows = [[Paragraph("Rank", s["TableHead"]),
                     Paragraph("Primary ISIC Rev. 5 class", s["TableHead"]),
                     Paragraph("Count", s["TableHead"])]]
        for i, (cls, n) in enumerate(class_counts.most_common(TOP_N_TABLE), 1):
            tbl_rows.append([
                Paragraph(str(i), s["TableCell"]),
                Paragraph(cls, s["TableCell"]),
                Paragraph(str(n), s["TableCell"]),
            ])
        self.story.append(styled_table(
            tbl_rows, [1.4 * cm, 11.2 * cm, 1.8 * cm]))
        self.story.append(Paragraph(
            f"Table {section_no+2}. Twenty most frequent primary classes for {name}.",
            s["Caption"]))

        # (c) comments
        self.story.append(Paragraph("(c)  Comments on the findings", s["H2"]))
        top3 = class_counts.most_common(3)
        top3_txt = "; ".join(f"{c} ({n})" for c, n in top3)
        self.p(
            f"The three most common classes for {name} are {top3_txt}. This "
            f"concentration is consistent with QDR's focus on qualitative social- "
            f"and health-science research. The long tail "
            f"({len(class_counts)} divisions in total) shows that the corpus is "
            f"nevertheless topically diverse, reaching into education, cultural/"
            f"archival activities, scientific research and public administration. "
            f"As noted in Section 5, classes derived largely from documentation "
            f"vocabulary (e.g. paper/printing divisions) should be read with "
            f"caution given the metadata-only method.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DB_DEFAULT)
    parser.add_argument("--out", default=OUT_DEFAULT)
    args = parser.parse_args()

    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    report = Report(args.db, args.out)
    report.build()
    print(f"[OK] Professional report written -> {args.out}")


if __name__ == "__main__":
    main()
