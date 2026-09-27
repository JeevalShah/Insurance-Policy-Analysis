import json
import re
import networkx as nx
from pyvis.network import Network
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity 

# =====================================================================
# 1. Expanded Mock Document Datasets (20 Total Documents)
# =====================================================================

RULE_DOCUMENTS = [
    {
        "id": "RuleChange:RC-2026-01_WaterDamage.txt",
        "filename": "RC-2026-01_WaterDamage.txt",
        "doc_type": "RuleChange",
        "effective_date": "2026-01-15",
        "impact_rating": "High",
        "text": """
        RULE CHANGE NOTICE RC-2026-01 (WATER DAMAGE):
        Pursuant to Section 12.1 and Clause 4.2, all residential and commercial property water damage claims require mandatory quarterly inspection reports.
        Payout limits for structural flooding are capped at $50,000 max. Any claims without quarterly inspection logs shall be rejected.
        """
    },
    {
        "id": "RuleChange:RC-2026-02_AutoTowing.txt",
        "filename": "RC-2026-02_AutoTowing.txt",
        "doc_type": "RuleChange",
        "effective_date": "2026-02-01",
        "impact_rating": "Medium",
        "text": """
        RULE CHANGE NOTICE RC-2026-02 (AUTO TOWING CAPS):
        Under Section 8.1, roadside recovery and emergency towing reimbursements are strictly capped at $100 per incident.
        Third-party unauthorized towing services are strictly non-compliant and non-reimbursable under revised underwriting guidelines.
        """
    },
    {
        "id": "RuleChange:RC-2026-03_CyberMFA.txt",
        "filename": "RC-2026-03_CyberMFA.txt",
        "doc_type": "RuleChange",
        "effective_date": "2026-03-01",
        "impact_rating": "Critical",
        "text": """
        RULE CHANGE NOTICE RC-2026-03 (CYBER SECURITY HARDENING):
        Referencing Paragraph 15.3, cyber liability coverage requires mandatory hardware-token multi-factor authentication (MFA) on administrator endpoints.
        Bi-annual third-party penetration testing reports must be submitted to underwriters annually.
        """
    },
    {
        "id": "RuleChange:RC-2026-04_HealthPreExisting.txt",
        "filename": "RC-2026-04_HealthPreExisting.txt",
        "doc_type": "RuleChange",
        "effective_date": "2026-04-10",
        "impact_rating": "Medium",
        "text": """
        RULE CHANGE NOTICE RC-2026-04 (PRE-EXISTING WAITING PERIODS):
        Amendment to Clause 9.4: The initial waiting period for pre-existing cardiovascular conditions is reduced from 24 months to 12 months.
        Co-pay percentages remain static at 15% across network hospitals.
        """
    },
    {
        "id": "RuleChange:RC-2026-05_RoofDepreciation.txt",
        "filename": "RC-2026-05_RoofDepreciation.txt",
        "doc_type": "RuleChange",
        "effective_date": "2026-05-20",
        "impact_rating": "High",
        "text": """
        RULE CHANGE NOTICE RC-2026-05 (ROOF AGE DEPRECIATION):
        Modifying Section 12.1 and Article 7: Roof replacement coverage for asphalt shingle roofs older than 15 years shall transition from Actual Replacement Value to Actual Cash Value (ACV).
        """
    },
    {
        "id": "RuleChange:RC-2026-06_SupplyChainDowntime.txt",
        "filename": "RC-2026-06_SupplyChainDowntime.txt",
        "doc_type": "RuleChange",
        "effective_date": "2026-06-01",
        "impact_rating": "High",
        "text": """
        RULE CHANGE NOTICE RC-2026-06 (BUSINESS INTERRUPTION WAITING PERIOD):
        Modifying Section 5.3: Contingent business interruption coverage resulting from Tier-1 vendor supply chain disruptions now requires a mandatory 72-hour waiting period before indemnity payments commence.
        """
    },
    {
        "id": "RuleChange:RC-2026-07_PFASPollutionExclusion.txt",
        "filename": "RC-2026-07_PFASPollutionExclusion.txt",
        "doc_type": "RuleChange",
        "effective_date": "2026-06-15",
        "impact_rating": "Critical",
        "text": """
        RULE CHANGE NOTICE RC-2026-07 (PFAS & CONTAMINANT EXCLUSION):
        Amending Clause 18.2: Comprehensive general liability policies shall completely exclude coverage for bodily injury or property damage arising out of Per- and Polyfluoroalkyl Substances (PFAS) contamination.
        """
    },
    {
        "id": "RuleChange:RC-2026-08_DOClawsuitDefense.txt",
        "filename": "RC-2026-08_DOClawsuitDefense.txt",
        "doc_type": "RuleChange",
        "effective_date": "2026-07-01",
        "impact_rating": "Medium",
        "text": """
        RULE CHANGE NOTICE RC-2026-08 (D&O REGULATORY DEFENSE SUB-LIMITS):
        Referencing Article 3: Defense costs for regulatory enforcement actions and SEC investigations are now subject to a strict $1,000,000 sub-limit per policy period.
        """
    },
    {
        "id": "RuleChange:RC-2026-09_CargoColdChain.txt",
        "filename": "RC-2026-09_CargoColdChain.txt",
        "doc_type": "RuleChange",
        "effective_date": "2026-07-20",
        "impact_rating": "High",
        "text": """
        RULE CHANGE NOTICE RC-2026-09 (MARITIME COLD CHAIN TEMPERATURE MONITORS):
        Under Section 11.4, temperature-sensitive refrigerated cargo claims require continuous IoT data logs proving temperatures did not exceed 4 degrees Celsius during transport.
        """
    },
    {
        "id": "RuleChange:RC-2026-10_ProductRecallDeductible.txt",
        "filename": "RC-2026-10_ProductRecallDeductible.txt",
        "doc_type": "RuleChange",
        "effective_date": "2026-08-05",
        "impact_rating": "Medium",
        "text": """
        RULE CHANGE NOTICE RC-2026-10 (PRODUCT RECALL MANDATORY DEDUCTIBLE):
        Amending Paragraph 22.1: First-party product recall expense coverage now carries a minimum mandatory deductible of $50,000 or 10% of total recall expenses, whichever is greater.
        """
    }
]

ACTUAL_DOCUMENTS = [
    {
        "id": "ActualPolicy:POL-PROP-2024_CommercialProperty.txt",
        "filename": "POL-PROP-2024_CommercialProperty.txt",
        "doc_type": "ActualPolicy",
        "policy_holder": "Apex Commercial Real Estate",
        "risk_level": "Medium",
        "text": """
        COMMERCIAL PROPERTY MASTER POLICY:
        Section 12.1 - Water Damage & Structural Overhead Coverage:
        Covers internal plumbing bursts up to $250,000 per occurrence. 
        Clause 4.2 - Inspection Terms: Policyholders must maintain semi-annual plumbing maintenance logs.
        Article 7 - Structural Additions: Roof replacements are covered under Full Replacement Cost without depreciation deduction.
        """
    },
    {
        "id": "ActualPolicy:POL-AUTO-2025_FleetAuto.txt",
        "filename": "POL-AUTO-2025_FleetAuto.txt",
        "doc_type": "ActualPolicy",
        "policy_holder": "LogiTech Fleet Operations",
        "risk_level": "High",
        "text": """
        COMMERCIAL FLEET AUTO POLICY:
        Section 8.1 - Emergency Roadside Recovery & Towing:
        Policyholders are fully covered for roadside recovery up to $500 per event, including third-party towing providers chosen by the driver.
        """
    },
    {
        "id": "ActualPolicy:POL-CYBER-2025_EnterpriseTech.txt",
        "filename": "POL-CYBER-2025_EnterpriseTech.txt",
        "doc_type": "ActualPolicy",
        "policy_holder": "CloudScale Systems LLC",
        "risk_level": "Critical",
        "text": """
        ENTERPRISE CYBER LIABILITY POLICY:
        Paragraph 15.3 - Security Safeguards & Identity Access Controls:
        Insured entity must maintain commercial-grade identity access management, software MFA, and annual internal vulnerability assessments.
        Excludes ransomware payout coverage if fundamental access policies are unverified.
        """
    },
    {
        "id": "ActualPolicy:POL-HLTH-2023_GroupHealth.txt",
        "filename": "POL-HLTH-2023_GroupHealth.txt",
        "doc_type": "ActualPolicy",
        "policy_holder": "Synergy Workforce Corp",
        "risk_level": "Low",
        "text": """
        GROUP HEALTH COMPREHENSIVE PLAN:
        Clause 9.4 - Pre-Existing Condition Exclusions:
        Pre-existing conditions including cardiac and diabetic ailments are subject to a strict 24-month waiting window from enrollment date.
        Co-pay rate is fixed at 15% in-network.
        """
    },
    {
        "id": "ActualPolicy:POL-EXEC-2025_DirectorsLiability.txt",
        "filename": "POL-EXEC-2025_DirectorsLiability.txt",
        "doc_type": "ActualPolicy",
        "policy_holder": "Vanguard Executive Board",
        "risk_level": "Medium",
        "text": """
        DIRECTORS & OFFICERS LIABILITY POLICY:
        Article 3 - Regulatory Non-Compliance & Legal Defense:
        Protects executive officers against shareholder lawsuits, regulatory audit penalties, and corporate governance disputes. Defense costs are covered up to the full aggregate policy limit of $5,000,000.
        Excludes coverage for deliberate fraudulent activity or unapproved policy modifications.
        """
    },
    {
        "id": "ActualPolicy:POL-BIZ-2024_SupplyChainInterruption.txt",
        "filename": "POL-BIZ-2024_SupplyChainInterruption.txt",
        "doc_type": "ActualPolicy",
        "policy_holder": "Global Logistics Hub Corp",
        "risk_level": "High",
        "text": """
        BUSINESS INTERRUPTION & CONTINGENT RISK POLICY:
        Section 5.3 - Vendor Supply Chain Downtime:
        Indemnifies lost net operating income following vendor operational shutdown. Indemnity payments begin immediately after a 24-hour elimination period.
        """
    },
    {
        "id": "ActualPolicy:POL-ENV-2025_GeneralPollution.txt",
        "filename": "POL-ENV-2025_GeneralPollution.txt",
        "doc_type": "ActualPolicy",
        "policy_holder": "ChemCorp Manufacturing",
        "risk_level": "Critical",
        "text": """
        ENVIRONMENTAL IMPAIRMENT & GENERAL LIABILITY POLICY:
        Clause 18.2 - Hazardous Substance Remediation:
        Covers legal defense and environmental clean-up costs for accidental chemical spills and industrial emissions, subject to standard hazardous material definitions.
        """
    },
    {
        "id": "ActualPolicy:POL-MAR-2024_OceanCargo.txt",
        "filename": "POL-MAR-2024_OceanCargo.txt",
        "doc_type": "ActualPolicy",
        "policy_holder": "Pacific Freight Line",
        "risk_level": "Medium",
        "text": """
        OCEAN CARGO & COLD CHAIN TRANSPORT POLICY:
        Section 11.4 - Perishable Freight & Refrigeration Failure:
        Protects against spoilage due to mechanical breakdown of refrigeration units. Requires manual temperature inspection logs recorded at origin and destination ports.
        """
    },
    {
        "id": "ActualPolicy:POL-PROD-2025_ManufacturerLiability.txt",
        "filename": "POL-PROD-2025_ManufacturerLiability.txt",
        "doc_type": "ActualPolicy",
        "policy_holder": "Apex Consumer Goods",
        "risk_level": "High",
        "text": """
        COMMERCIAL PRODUCT LIABILITY PLAN:
        Paragraph 22.1 - Product Recall & Withdrawal Expenses:
        Reimburses costs for public notice, shipping, and destruction of defective products. Policy deductible is set at a flat $10,000 per recall event.
        """
    },
    {
        "id": "ActualPolicy:POL-CONSTR-2023_BuildersRisk.txt",
        "filename": "POL-CONSTR-2023_BuildersRisk.txt",
        "doc_type": "ActualPolicy",
        "policy_holder": "Skyline Construction Group",
        "risk_level": "Medium",
        "text": """
        BUILDERS RISK & INFRASTRUCTURE COVERAGE:
        Section 14.1 - Weather Damage & Site Preservation:
        Covers physical damage to structures under construction caused by windstorm, hail, or unexpected structural collapse.
        """
    }
]

# Create directed graph
G = nx.DiGraph()

# Ingest Nodes
all_docs = RULE_DOCUMENTS + ACTUAL_DOCUMENTS
for doc in all_docs:
    G.add_node(
        doc["id"],
        label=doc["filename"],
        type=doc["doc_type"],
        text=doc["text"],
        filename=doc["filename"],
        effective_date=doc.get("effective_date", "N/A"),
        impact_rating=doc.get("impact_rating", "N/A"),
        risk_level=doc.get("risk_level", "N/A")
    )

print(f"Graph initialized with {len(RULE_DOCUMENTS)} Rule Changes and {len(ACTUAL_DOCUMENTS)} Actual Policies.")

# =====================================================================
# 2. Extract Explicit Reference Links & Classify Compliance Status
# =====================================================================
REFERENCE_REGEX = r"(?:section|clause|policy|item|article|paragraph)\s*#?\s*(\d+(?:\.\d+)*[a-z]?)"

explicit_links_count = 0

for r_doc in RULE_DOCUMENTS:
    matches = re.findall(REFERENCE_REGEX, r_doc["text"], flags=re.IGNORECASE)
    for target_clause in set(matches):
        for a_doc in ACTUAL_DOCUMENTS:
            if target_clause.lower() in a_doc["text"].lower():
                
                r_text = r_doc["text"].lower()
                a_text = a_doc["text"].lower()

                if "$100" in r_text and "$500" in a_text:
                    status = "NON_COMPLIANT_CONFLICT"
                    reason = f"Cap mismatch on {target_clause} ($100 rule vs $500 policy limit)"
                elif "hardware-token" in r_text and "software mfa" in a_text:
                    status = "PARTIAL_UNDER_INSURED"
                    reason = f"Security spec gap on {target_clause} (Hardware Token required vs Software MFA in place)"
                elif "12 months" in r_text and "24 months" in a_text:
                    status = "BENEFICIAL_UPDATE"
                    reason = f"Waiting period reduced on {target_clause} (Rule: 12m vs Policy: 24m)"
                elif "actual cash value" in r_text and "full replacement cost" in a_text:
                    status = "NON_COMPLIANT_CONFLICT"
                    reason = f"Valuation conflict on {target_clause} (ACV required vs Full Replacement Cost in policy)"
                elif "72-hour" in r_text and "24-hour" in a_text:
                    status = "NON_COMPLIANT_CONFLICT"
                    reason = f"Waiting period mismatch on {target_clause} (Rule requires 72h vs Policy 24h)"
                elif "pfas" in r_text:
                    status = "NON_COMPLIANT_CONFLICT"
                    reason = f"New exclusion on {target_clause} (Rule excludes PFAS contaminants)"
                elif "sub-limit" in r_text and "aggregate policy limit" in a_text:
                    status = "PARTIAL_UNDER_INSURED"
                    reason = f"Sub-limit restriction on {target_clause} ($1M sub-limit vs $5M aggregate limit)"
                elif "iot data logs" in r_text and "manual temperature inspection" in a_text:
                    status = "PARTIAL_UNDER_INSURED"
                    reason = f"Monitoring gap on {target_clause} (Continuous IoT required vs Manual logs in policy)"
                elif "$50,000" in r_text and "$10,000" in a_text:
                    status = "NON_COMPLIANT_CONFLICT"
                    reason = f"Deductible gap on {target_clause} ($50k rule deductible vs $10k policy deductible)"
                else:
                    status = "COMPLIANT_MATCH"
                    reason = f"Explicit alignment on clause match {target_clause}"

                G.add_edge(
                    r_doc["id"],
                    a_doc["id"],
                    relation="EXPLICIT_REF",
                    match=f"Clause {target_clause}",
                    status=status,
                    reason=reason,
                    weight=3.0
                )
                explicit_links_count += 1

print(f"Identified {explicit_links_count} explicit clause reference relationships.")

# =====================================================================
# 3. Compute Semantic Similarity (TF-IDF Similarity Matrix)
# =====================================================================
SIMILARITY_THRESHOLD = 0.15

rule_texts = [d["text"] for d in RULE_DOCUMENTS]
actual_texts = [d["text"] for d in ACTUAL_DOCUMENTS]

vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
tfidf_matrix = vectorizer.fit_transform(rule_texts + actual_texts)

rule_vectors = tfidf_matrix[: len(RULE_DOCUMENTS)]
actual_vectors = tfidf_matrix[len(RULE_DOCUMENTS) :]

sim_matrix = cosine_similarity(rule_vectors, actual_vectors)

implicit_links_count = 0
for i, r_doc in enumerate(RULE_DOCUMENTS):
    for j, a_doc in enumerate(ACTUAL_DOCUMENTS):
        score = float(sim_matrix[i, j])
        if score >= SIMILARITY_THRESHOLD and not G.has_edge(r_doc["id"], a_doc["id"]):
            G.add_edge(
                r_doc["id"],
                a_doc["id"],
                relation="IMPLICIT_SIMILAR",
                score=round(score, 3),
                status="SEMANTIC_OVERLAP",
                reason=f"TF-IDF overlap score: {round(score, 3)}",
                weight=round(score * 2, 2)
            )
            implicit_links_count += 1

print(f"Identified {implicit_links_count} semantic similarity relationships.")

# =====================================================================
# 4. Generate Interactive Visualization with Pyvis
# =====================================================================
net = Network(height="850px", width="100%", directed=True, notebook=False)

NODE_COLORS = {
    "RuleChange": "#E74C3C",     # Red-coral for rule updates
    "ActualPolicy": "#2980B9"    # Strong blue for active policies
}

EDGE_COLORS = {
    "COMPLIANT_MATCH": "#2ECC71",         # Bright Green
    "BENEFICIAL_UPDATE": "#27AE60",       # Dark Green
    "NON_COMPLIANT_CONFLICT": "#C0392B",  # Deep Red
    "PARTIAL_UNDER_INSURED": "#E67E22",  # Orange
    "SEMANTIC_OVERLAP": "#BDC3C7"        # Grey dashed line
}

for node_id, attrs in G.nodes(data=True):
    doc_type = attrs.get("type", "Unknown")
    filename = attrs.get("filename", node_id)
    snippet = attrs.get("text", "").strip().replace("\n", "<br>")
    
    hover_tooltip = f"""
    <div style="font-family: Arial, sans-serif; width: 320px; padding: 6px;">
        <b style="font-size: 14px; color:{NODE_COLORS.get(doc_type, '#333')}">[{doc_type.upper()}]</b><br>
        <b>File:</b> {filename}<br>
        <b>Impact / Risk:</b> {attrs.get('impact_rating', attrs.get('risk_level', 'N/A'))}<br>
        <hr style="border: 0.5px solid #ccc; margin: 6px 0;">
        <b>Content Excerpt:</b><br>
        <i style="font-size: 11px; color: #555;">{snippet}</i>
    </div>
    """
    
    net.add_node(
        node_id,
        label=filename.split(".")[0],
        title=hover_tooltip,
        color=NODE_COLORS.get(doc_type, "#999999"),
        shape="dot",
        size=26 if doc_type == "RuleChange" else 20
    )

for u, v, attrs in G.edges(data=True):
    status = attrs.get("status", "SEMANTIC_OVERLAP")
    rel = attrs.get("relation", "")
    reason = attrs.get("reason", "")
    
    if rel == "EXPLICIT_REF":
        title = f"<b>{attrs.get('match')}</b><br>Status: {status}<br>Detail: {reason}"
        width = 4
        dashes = False
    else:
        title = f"<b>Semantic Link</b><br>Score: {attrs.get('score')}<br>Detail: {reason}"
        width = 1.5
        dashes = True
        
    net.add_edge(
        u, 
        v, 
        title=title, 
        color=EDGE_COLORS.get(status, "#CCCCCC"), 
        width=width,
        dashes=dashes
    )

net.set_options("""
var options = {
  "physics": {
    "barnesHut": {
      "gravitationalConstant": -15000,
      "centralGravity": 0.2,
      "springLength": 220,
      "springConstant": 0.03
    },
    "minVelocity": 0.75
  }
}
""")

output_html = "policy_relationship_graph.html"
net.show(output_html, notebook=False)

# =====================================================================
# 5. Export JSON to Disk
# =====================================================================
from networkx.readwrite import json_graph

graph_json_path = "policy_knowledge_graph.json"
with open(graph_json_path, "w") as f:
    json.dump(json_graph.node_link_data(G), f, indent=2)

print(f"\nGraph generated with {len(G.nodes())} nodes and {len(G.edges())} edges.")
print(f"1. Open '{output_html}' in your browser to inspect visual node clusters.")
print(f"2. Graph output saved to '{graph_json_path}'.")