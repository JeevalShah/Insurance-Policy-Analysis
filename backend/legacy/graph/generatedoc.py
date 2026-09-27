import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_hex):
    """Sets background color for a table cell."""
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Sets internal padding for a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def create_documentation():
    doc = Document()

    # --- Page Margins ---
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # --- Color Palette Constants ---
    NAVY = RGBColor(31, 78, 121)       # Primary Accent #1F4E79
    SLATE = RGBColor(89, 89, 89)       # Secondary Accent #595959
    DARK_TEXT = RGBColor(38, 38, 38)   # Primary Text #262626
    WHITE = RGBColor(255, 255, 255)

    # --- Document Title ---
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(4)
    run_title = p_title.add_run("Insurance Policy & Regulatory Compliance")
    run_title.font.name = 'Arial'
    run_title.font.size = Pt(22)
    run_title.font.bold = True
    run_title.font.color.rgb = NAVY

    p_subtitle = doc.add_paragraph()
    p_subtitle.paragraph_format.space_before = Pt(0)
    p_subtitle.paragraph_format.space_after = Pt(20)
    run_sub = p_subtitle.add_run("Knowledge Graph Architecture & Technical Specification")
    run_sub.font.name = 'Arial'
    run_sub.font.size = Pt(14)
    run_sub.font.color.rgb = SLATE

    # Helper for Section Headings
    def add_heading_1(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(18)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.name = 'Arial'
        run.font.size = Pt(15)
        run.font.bold = True
        run.font.color.rgb = NAVY
        return p

    def add_heading_2(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.name = 'Arial'
        run.font.size = Pt(12)
        run.font.bold = True
        run.font.color.rgb = SLATE
        return p

    def add_body_p(text, bold_prefix=None, space_after=6):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.line_spacing = 1.15
        if bold_prefix:
            r_bold = p.add_run(bold_prefix)
            r_bold.font.name = 'Arial'
            r_bold.font.size = Pt(10)
            r_bold.font.bold = True
            r_bold.font.color.rgb = DARK_TEXT
        r_text = p.add_run(text)
        r_text.font.name = 'Arial'
        r_text.font.size = Pt(10)
        r_text.font.color.rgb = DARK_TEXT
        return p

    def add_code_block(code_text):
        table = doc.add_table(rows=1, cols=1)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = table.cell(0, 0)
        cell.width = Inches(6.5)
        set_cell_background(cell, "F2F2F2")
        set_cell_margins(cell, top=120, bottom=120, left=180, right=180)
        
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(code_text.strip())
        run.font.name = 'Consolas'
        run.font.size = Pt(9)
        run.font.color.rgb = DARK_TEXT

        # Add spacing after code block
        p_space = doc.add_paragraph()
        p_space.paragraph_format.space_before = Pt(0)
        p_space.paragraph_format.space_after = Pt(6)

    # --- 1. Executive Overview ---
    add_heading_1("1. Executive Overview")
    add_body_p(
        "The Insurance Policy & Regulatory Compliance Knowledge Graph is an automated graph-based analysis pipeline "
        "designed to resolve compliance gaps, financial risk discrepancies, and semantic overlaps between updated "
        "Rule Change Notices (RULE_DOCUMENTS) and active Insurance Policy Contracts (ACTUAL_DOCUMENTS). "
        "By processing textual document structures through regex-based clause tracking and NLP-driven semantic vectorization, "
        "the pipeline identifies operational mismatches (e.g., restricted payout limits, omitted MFA security mandates, "
        "or conflicting valuation models) before claims are filed."
    )

    # --- 2. Data Schema & Node Architecture ---
    add_heading_1("2. Data Schema & Node Architecture")
    add_body_p("The knowledge graph represents entities and relationships using a directed graph structure, denoted as G = (V, E).")
    
    add_code_block("[ RuleChange ] ── (EXPLICIT_REF / IMPLICIT_SIMILAR) ──> [ ActualPolicy ]")

    add_heading_2("Node Definitions")
    
    add_body_p(
        "Represents new or amended underwriting directives, regulatory guidelines, and standard endorsement modifications issued by regulatory or internal committees.",
        bold_prefix="1. RuleChange Nodes: "
    )
    add_body_p("id (String): Unique identifier (e.g., RuleChange:RC-2026-01_WaterDamage.txt)")
    add_body_p("filename (String): Document filename")
    add_body_p("doc_type (String): Always set to 'RuleChange'")
    add_body_p("effective_date (String - ISO 8601): Date the directive takes effect")
    add_body_p("impact_rating (String): Mandatory severity score ('Medium', 'High', or 'Critical')")
    add_body_p("text (String): Plaintext content of the update notice", space_after=10)

    add_body_p(
        "Active insurance contracts bound to institutional policyholders.",
        bold_prefix="2. ActualPolicy Nodes: "
    )
    add_body_p("id (String): Unique identifier (e.g., ActualPolicy:POL-PROP-2024_CommercialProperty.txt)")
    add_body_p("filename (String): Policy document filename")
    add_body_p("doc_type (String): Always set to 'ActualPolicy'")
    add_body_p("policy_holder (String): Entity holding the policy contract")
    add_body_p("risk_level (String): Policy risk assessment ('Low', 'Medium', 'High', 'Critical')")
    add_body_p("text (String): Plaintext clause definitions", space_after=12)

    # --- 3. Edge Relationships & Classification Taxonomy ---
    add_heading_1("3. Edge Relationships & Classification Taxonomy")
    add_body_p("Edges represent directed relationships originating from a RuleChange directive and terminating at an ActualPolicy document.")

    # Table: Edge Taxonomy
    table_data = [
        ("Relation Type", "Status", "Visual Style", "Color Code", "Trigger Condition"),
        ("EXPLICIT_REF", "NON_COMPLIANT_CONFLICT", "Solid Line (Thick)", "Deep Red (#C0392B)", "Hard limit mismatch, exclusion addition, or valuation model conflict on explicit clause reference."),
        ("EXPLICIT_REF", "PARTIAL_UNDER_INSURED", "Solid Line (Thick)", "Orange (#E67E22)", "Operational security gap, sub-limit cap, or monitoring/inspection delta on explicit clause match."),
        ("EXPLICIT_REF", "BENEFICIAL_UPDATE", "Solid Line (Thick)", "Dark Green (#27AE60)", "Favorable policyholder adjustment (e.g., waiting period reduction)."),
        ("EXPLICIT_REF", "COMPLIANT_MATCH", "Solid Line (Thick)", "Bright Green (#2ECC71)", "Fully aligned terms across explicit clause references."),
        ("IMPLICIT_SIMILAR", "SEMANTIC_OVERLAP", "Dashed Line (Thin)", "Grey (#BDC3C7)", "No explicit clause citation, but cosine similarity score S_TFIDF >= 0.15.")
    ]

    table = doc.add_table(rows=len(table_data), cols=5)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    
    col_widths = [Inches(1.1), Inches(1.5), Inches(1.1), Inches(1.1), Inches(1.7)]

    for row_idx, row_values in enumerate(table_data):
        row = table.rows[row_idx]
        is_header = (row_idx == 0)
        
        for col_idx, text in enumerate(row_values):
            cell = row.cells[col_idx]
            cell.width = col_widths[col_idx]
            set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
            
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(text)
            run.font.name = 'Arial'
            run.font.size = Pt(8.5)
            
            if is_header:
                set_cell_background(cell, "1F4E79")
                run.font.bold = True
                run.font.color.rgb = WHITE
            else:
                if row_idx % 2 == 1:
                    set_cell_background(cell, "FFFFFF")
                else:
                    set_cell_background(cell, "F9F9F9")
                run.font.color.rgb = DARK_TEXT

    p_table_space = doc.add_paragraph()
    p_table_space.paragraph_format.space_before = Pt(0)
    p_table_space.paragraph_format.space_after = Pt(12)

    # --- 4. Edge Resolution Pipeline ---
    add_heading_1("4. Edge Resolution Pipeline")
    
    add_code_block(
"""Rule Change Text & Actual Policy Text
                 │
       ┌─────────┴─────────┐
       ▼                   ▼
[ Regex Matcher ]   [ TF-IDF Vectorizer ]
       │                   │
Explicit Clause Ref?   Cosine Sim >= 0.15?
├── YES: EXPLICIT      └── YES: IMPLICIT
└── NO: Check TF-IDF   └── NO: Discard"""
    )

    add_heading_2("1. Explicit Reference Parsing")
    add_body_p(
        "Direct legal cross-references are captured via standard regular expressions matching target policy legal structures:"
    )
    add_code_block(r'RegEx Pattern = "(?:Section|Clause|Policy|Item|Article|Paragraph)\s*#?\s*(\d+(?:\.\d+)*[a-z]?)"')
    add_body_p(
        "Upon detecting a clause overlap (e.g., Section 12.1), comparative logic evaluates parameter differences to assign one of four compliance statuses (NON_COMPLIANT_CONFLICT, PARTIAL_UNDER_INSURED, BENEFICIAL_UPDATE, or COMPLIANT_MATCH)."
    )

    add_heading_2("2. Semantic Similarity Mapping")
    add_body_p(
        "To discover unlinked or implicit operational overlaps, document texts are processed through Term Frequency-Inverse Document Frequency (TF-IDF) representation using unigrams and bigrams. "
        "Pairwise similarity between Rule Change vectors and Policy vectors is computed via Cosine Similarity. "
        "If Similarity Score >= 0.15 and no explicit reference edge exists, an IMPLICIT_SIMILAR relationship is constructed."
    )

    # --- 5. Graph Document Pairings Map ---
    add_heading_1("5. Graph Document Pairings Map")
    add_body_p("The knowledge graph actively tracks 10 Primary Vulnerability Cross-Links across the dataset:")

    pairings = [
        ("[RC-2026-01: Water Damage] ── (Section 12.1 / Clause 4.2) ──> [POL-PROP-2024: Commercial Property]",
         "Conflict: $50,000 cap & quarterly inspection logs vs $250,000 limit & semi-annual logs."),
        ("[RC-2026-02: Auto Towing] ── (Section 8.1) ──> [POL-AUTO-2025: Fleet Auto]",
         "Conflict: $100 cap & unauthorized towing ban vs $500 cap & open third-party provider selection."),
        ("[RC-2026-03: Cyber MFA] ── (Paragraph 15.3) ──> [POL-CYBER-2025: Enterprise Tech]",
         "Gap: Hardware-token MFA & bi-annual pentests required vs Software MFA & annual internal audits."),
        ("[RC-2026-04: Pre-Existing] ── (Clause 9.4) ──> [POL-HLTH-2023: Group Health]",
         "Beneficial: 12-month waiting period reduction vs existing 24-month restriction."),
        ("[RC-2026-05: Roof Depreciation] ── (Article 7 / Section 12.1) ──> [POL-PROP-2024: Commercial Property]",
         "Conflict: Actual Cash Value (ACV) for roofs >15 yrs vs Full Replacement Cost without depreciation."),
        ("[RC-2026-06: Business Interruption] ── (Section 5.3) ──> [POL-BIZ-2024: Supply Chain]",
         "Conflict: Mandatory 72-hour waiting period vs 24-hour elimination period."),
        ("[RC-2026-07: PFAS Contamination] ── (Clause 18.2) ──> [POL-ENV-2025: General Pollution]",
         "Conflict: Complete PFAS exclusion vs standard hazardous material remediation coverage."),
        ("[RC-2026-08: D&O Legal Defense] ── (Article 3) ──> [POL-EXEC-2025: Directors Liability]",
         "Gap: $1,000,000 regulatory defense sub-limit vs $5,000,000 full aggregate policy limit."),
        ("[RC-2026-09: Cold Chain Cargo] ── (Section 11.4) ──> [POL-MAR-2024: Ocean Cargo]",
         "Gap: Continuous IoT temperature logs required vs manual logging at origin/destination ports."),
        ("[RC-2026-10: Product Recall] ── (Paragraph 22.1) ──> [POL-PROD-2025: Manufacturer Liability]",
         "Conflict: $50,000 or 10% minimum mandatory deductible vs flat $10,000 policy deductible.")
    ]

    for link, desc in pairings:
        p_link = doc.add_paragraph()
        p_link.paragraph_format.space_before = Pt(4)
        p_link.paragraph_format.space_after = Pt(1)
        r_link = p_link.add_run(link)
        r_link.font.name = 'Consolas'
        r_link.font.size = Pt(8.5)
        r_link.font.bold = True
        r_link.font.color.rgb = NAVY

        p_desc = doc.add_paragraph()
        p_desc.paragraph_format.space_before = Pt(0)
        p_desc.paragraph_format.space_after = Pt(6)
        p_desc.paragraph_format.left_indent = Inches(0.25)
        r_desc = p_desc.add_run(f"└─ {desc}")
        r_desc.font.name = 'Arial'
        r_desc.font.size = Pt(9.5)
        r_desc.font.color.rgb = DARK_TEXT

    # --- 6. Programmatic Outputs ---
    add_heading_1("6. Programmatic Outputs")
    add_body_p("1. policy_knowledge_graph.json: Node-link JSON dataset optimized for downstream graph database ingestion (Neo4j, Amazon Neptune) or custom frontend visualizers.")
    add_body_p("2. policy_relationship_graph.html: Self-contained PyVis interactive HTML interface configured with Barnes-Hut force-directed physics layout algorithms.")

    # Save output document
    doc_path = "Insurance_Knowledge_Graph_Documentation.docx"
    doc.save(doc_path)
    print(f"Documentation successfully compiled and saved to '{doc_path}'.")

if __name__ == "__main__":
    create_documentation()