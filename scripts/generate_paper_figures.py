"""
generate_paper_figures.py
=========================
Generates 6 publication-quality figures for the Sentra Engine research paper.

Usage (from repo root, with venv active):
    python scripts/generate_paper_figures.py

Outputs are written to scripts/figures/ at 300 DPI.
"""

from __future__ import annotations

import os
import math
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless rendering — no display required
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

# ── output directory ─────────────────────────────────────────────────────────
OUT_DIR = Path(__file__).resolve().parent / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── shared style ─────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "figure.dpi": 150,
    "savefig.dpi": 300,
})

COLORS = {
    "legacy":   "#c0392b",
    "flask":    "#2980b9",
    "neo4j":    "#27ae60",
    "policy":   "#2ecc71",
    "reg":      "#e74c3c",
    "arrow":    "#555555",
    "faiss":    "#8e44ad",
    "llm":      "#e67e22",
    "bg":       "#f8f9fa",
    "border":   "#dee2e6",
}

SAVE_KW = dict(bbox_inches="tight", dpi=300)


# ═══════════════════════════════════════════════════════════════════════════════
# Figure 1 — Three-Stage Architecture Evolution
# ═══════════════════════════════════════════════════════════════════════════════
def fig1_architecture_evolution():
    fig, axes = plt.subplots(1, 3, figsize=(17, 7))
    fig.patch.set_facecolor(COLORS["bg"])
    fig.suptitle("Figure 1: Sentra Engine — Three-Stage Architecture Evolution",
                 fontsize=14, fontweight="bold", y=1.01)

    stages = [
        {
            "title": "Stage 1\nLegacy CLI",
            "color": COLORS["legacy"],
            "components": [
                ("Global Files", ["faiss_index.bin", "structured_clauses.json"], "#fadbd8"),
                ("Hardcoded Graph", ["dependency_dict (Python dict)", "BFS: get_indirect_impacts()"], "#f9ebea"),
                ("Output", ["Terminal / JSON stdout"], "#fdfefe"),
            ],
        },
        {
            "title": "Stage 2\nOptimized Flask / React",
            "color": COLORS["flask"],
            "components": [
                ("Session Isolation", ["services/session_store.py", "UUID-keyed sessions"], "#d6eaf8"),
                ("Per-Session FAISS", ["IndexFlatL2 (nomic-embed-text)", "Regex clause parsing"], "#d6eaf8"),
                ("In-Memory Graph", ["NetworkX DiGraph", "BFS traversal (RAM only)"], "#eaf4fb"),
                ("API", ["Flask REST  ←→  React UI"], "#fdfefe"),
            ],
        },
        {
            "title": "Stage 3\nNeo4j Knowledge Graph",
            "color": COLORS["neo4j"],
            "components": [
                ("Persistent Store", ["graph_store.py", "bolt://localhost:7687"], "#d5f5e3"),
                ("Node Labels", ["RegulatoryClause", "PolicyClause"], "#d5f5e3"),
                ("Relationships", ["DEPENDS_ON", "CONFLICTS_WITH", "COMPLIES_WITH", "SUPPORTS", "IS_REDUNDANT"], "#a9dfbf"),
                ("Queries", ["Variable-length Cypher", "MATCH (r)-[*1..3]->(p)"], "#fdfefe"),
            ],
        },
    ]

    for ax, stage in zip(axes, stages):
        ax.set_facecolor(COLORS["bg"])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

        # Header box
        header = FancyBboxPatch((0.05, 0.86), 0.90, 0.11,
                                boxstyle="round,pad=0.02",
                                facecolor=stage["color"], edgecolor="white",
                                linewidth=2, zorder=3)
        ax.add_patch(header)
        ax.text(0.50, 0.918, stage["title"], ha="center", va="center",
                fontsize=12, fontweight="bold", color="white", zorder=4)

        y = 0.80
        for group_title, items, bg in stage["components"]:
            h = 0.055 + 0.038 * len(items)
            box = FancyBboxPatch((0.05, y - h), 0.90, h,
                                 boxstyle="round,pad=0.015",
                                 facecolor=bg, edgecolor=stage["color"],
                                 linewidth=1.2, zorder=2)
            ax.add_patch(box)
            ax.text(0.10, y - 0.015, group_title,
                    fontsize=9, fontweight="bold", color=stage["color"],
                    va="top", zorder=3)
            for i, item in enumerate(items):
                ax.text(0.14, y - 0.038 - i * 0.034, f"• {item}",
                        fontsize=7.5, va="top", color="#2c3e50", zorder=3)
            y -= h + 0.025

    # Evolution arrows between subplots
    for i in range(2):
        fig.add_artist(
            FancyArrowPatch(
                (axes[i].get_position().x1 - 0.005,
                 axes[i].get_position().y0 + axes[i].get_position().height / 2),
                (axes[i + 1].get_position().x0 + 0.005,
                 axes[i + 1].get_position().y0 + axes[i + 1].get_position().height / 2),
                transform=fig.transFigure,
                arrowstyle="->",
                mutation_scale=22,
                color="#555",
                linewidth=2,
            )
        )

    path = OUT_DIR / "fig1_architecture_evolution.png"
    fig.savefig(path, **SAVE_KW)
    plt.close(fig)
    print(f"  ✓  {path.name}")


# ═══════════════════════════════════════════════════════════════════════════════
# Figure 2 — Property-Graph Schema Diagram
# ═══════════════════════════════════════════════════════════════════════════════
def fig2_neo4j_schema():
    fig, ax = plt.subplots(figsize=(13, 6))
    fig.patch.set_facecolor(COLORS["bg"])
    ax.set_facecolor(COLORS["bg"])
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title("Figure 2: Neo4j Property-Graph Schema (Sentra Engine)",
                 fontsize=13, fontweight="bold", pad=14)

    def node_box(cx, cy, label, props, color, width=2.8, height=2.0):
        # Header
        hdr = FancyBboxPatch((cx - width / 2, cy + height / 2 - 0.45),
                              width, 0.45, boxstyle="round,pad=0.04",
                              facecolor=color, edgecolor=color, linewidth=0)
        ax.add_patch(hdr)
        ax.text(cx, cy + height / 2 - 0.22, label,
                ha="center", va="center", fontsize=10, fontweight="bold",
                color="white")
        # Body
        body = FancyBboxPatch((cx - width / 2, cy - height / 2),
                               width, height - 0.45,
                               boxstyle="round,pad=0.04",
                               facecolor="white", edgecolor=color, linewidth=2)
        ax.add_patch(body)
        for i, (pname, ptype) in enumerate(props):
            yp = cy + height / 2 - 0.65 - i * 0.30
            ax.text(cx - width / 2 + 0.12, yp,
                    f"{pname}:", fontsize=8, color="#555", va="center")
            ax.text(cx + width / 2 - 0.12, yp,
                    ptype, fontsize=8, color=color, va="center", ha="right",
                    style="italic")

    # PolicyClause node (left)
    node_box(2.0, 3.0, ":PolicyClause",
             [("id", "String"),
              ("session_id", "String"),
              ("text", "String"),
              ("section", "String"),
              ("source_doc", "String")],
             COLORS["policy"])

    # PolicyClause node (right — target of DEPENDS_ON)
    node_box(8.0, 3.0, ":PolicyClause",
             [("id", "String"),
              ("session_id", "String"),
              ("text", "String"),
              ("section", "String"),
              ("source_doc", "String")],
             COLORS["policy"])

    # RegulatoryClause node (bottom-centre)
    node_box(5.0, 0.8, ":RegulatoryClause",
             [("id", "String"),
              ("session_id", "String"),
              ("text", "String"),
              ("source_doc", "String")],
             COLORS["reg"])

    # DEPENDS_ON arrow (left PC → right PC)
    ax.annotate("", xy=(6.6, 3.0), xytext=(3.4, 3.0),
                arrowprops=dict(arrowstyle="->", color=COLORS["neo4j"],
                                lw=2.0, connectionstyle="arc3,rad=0.0"))
    ax.text(5.0, 3.22, "[:DEPENDS_ON]",
            ha="center", fontsize=9, fontweight="bold", color=COLORS["neo4j"])

    # COMPLIANCE edges (Reg → left PC)
    ax.annotate("", xy=(2.6, 1.9), xytext=(4.4, 1.3),
                arrowprops=dict(arrowstyle="->", color=COLORS["reg"],
                                lw=2.0, connectionstyle="arc3,rad=-0.25"))
    ax.text(3.1, 1.52,
            "[:CONFLICTS_WITH]\n[:COMPLIES_WITH]\n[:SUPPORTS]\n[:IS_REDUNDANT]",
            ha="center", fontsize=7.5, color=COLORS["reg"], linespacing=1.5)
    # edge property annotation
    ax.text(2.3, 0.65,
            "{classified_at, reasoning, label}",
            ha="center", fontsize=7.5, color="#666",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=COLORS["reg"], lw=1))

    # Index annotations
    idx_txt = ("Composite indexes:\n"
               "• (RegulatoryClause.id, session_id)\n"
               "• (PolicyClause.id, session_id)")
    ax.text(0.15, 0.25, idx_txt, fontsize=7.5, color="#444",
            va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", fc="#fffde7", ec="#f0c040", lw=1))

    path = OUT_DIR / "fig2_neo4j_schema.png"
    fig.savefig(path, **SAVE_KW)
    plt.close(fig)
    print(f"  ✓  {path.name}")


# ═══════════════════════════════════════════════════════════════════════════════
# Figure 3 — Graph-Aware RAG Architecture Flow
# ═══════════════════════════════════════════════════════════════════════════════
def fig3_graph_rag_flow():
    fig, ax = plt.subplots(figsize=(15, 6))
    fig.patch.set_facecolor(COLORS["bg"])
    ax.set_facecolor(COLORS["bg"])
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title("Figure 3: Graph-Aware RAG Architecture (chat_service.py)",
                 fontsize=13, fontweight="bold", pad=12)

    def pill(cx, cy, text, color, w=2.2, h=0.70, fc=None):
        fc = fc or color + "22"  # translucent fill
        box = FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                             boxstyle="round,pad=0.08",
                             facecolor=fc, edgecolor=color, linewidth=1.8)
        ax.add_patch(box)
        for i, line in enumerate(text.split("\n")):
            ax.text(cx, cy + 0.14 * (len(text.split("\n")) - 1) / 2 - i * 0.26,
                    line, ha="center", va="center",
                    fontsize=8.5, color="#2c3e50", fontweight="bold")

    def arrow(x0, y0, x1, y1, label="", rad=0.0, color="#555"):
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.8,
                                   connectionstyle=f"arc3,rad={rad}"))
        if label:
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2 + 0.18
            ax.text(mx, my, label, fontsize=7.5, ha="center", color=color)

    # Row positions
    y_main = 3.0
    y_faiss = 4.3
    y_neo4j = 1.7

    # 1 — User Query
    pill(1.3, y_main, "User\nQuery", "#555555", w=1.6, h=0.9)

    # 2 — Embedding / encode
    pill(3.4, y_main, "Encode Query\nnomic-embed-text", COLORS["faiss"], w=2.4)
    arrow(2.1, y_main, 2.2, y_main)

    # 3a — FAISS retrieval (top lane)
    pill(6.0, y_faiss, "FAISS Search\nIndexFlatL2  k=5", COLORS["faiss"], w=2.6)
    arrow(4.6, y_main + 0.2, 4.7, y_faiss, rad=-0.3, color=COLORS["faiss"])

    # 3b — Neo4j retrieval (bottom lane)
    pill(6.0, y_neo4j, "Neo4j Structural\nget_graph_impacts()", COLORS["neo4j"], w=2.6)
    arrow(4.6, y_main - 0.2, 4.7, y_neo4j, rad=0.3, color=COLORS["neo4j"])

    # FAISS sub-labels
    ax.text(6.0, y_faiss - 0.6, "Semantic similarity hits\n(session_store.py retriever)",
            ha="center", fontsize=7, color=COLORS["faiss"])

    # Neo4j sub-labels
    ax.text(6.0, y_neo4j - 0.6,
            "DEPENDS_ON (1–3 hops)\nCONFLICTS_WITH / COMPLIES_WITH / SUPPORTS",
            ha="center", fontsize=7, color=COLORS["neo4j"])

    # 4 — Merge context
    pill(9.4, y_main, "Merge Context\n& De-duplicate", "#7f8c8d", w=2.4)
    arrow(7.3, y_faiss, 8.2, y_main + 0.25, rad=0.3, color=COLORS["faiss"])
    arrow(7.3, y_neo4j, 8.2, y_main - 0.25, rad=-0.3, color=COLORS["neo4j"])

    # 5 — LLM
    pill(12.2, y_main, "Llama 3\n(Ollama local)", COLORS["llm"], w=2.4, h=0.9,
         fc="#fef9e7")
    arrow(10.6, y_main, 11.0, y_main)

    # 6 — Response
    pill(14.4, y_main, "Explanation\n& Compliance\nReport", "#2c3e50", w=1.8, h=1.1,
         fc="#eaf0fb")
    arrow(13.4, y_main, 13.5, y_main)

    # Brace labels
    ax.text(6.0, 5.4, "Parallel Retrieval Branches",
            ha="center", fontsize=9, fontweight="bold", color="#444",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#bbb"))

    path = OUT_DIR / "fig3_graph_rag_flow.png"
    fig.savefig(path, **SAVE_KW)
    plt.close(fig)
    print(f"  ✓  {path.name}")


# ═══════════════════════════════════════════════════════════════════════════════
# Figure 4 — Legacy vs. Optimized First-Stage Performance
# ═══════════════════════════════════════════════════════════════════════════════
def fig4_first_stage_benchmark():
    scenarios = ["Small\n(C=5, K=3)", "Medium\n(C=15, K=5)", "Large\n(C=30, K=8)"]
    # End-to-end latency (seconds): Legacy CLI vs. Optimized Flask/React
    legacy_e2e   = [15.0,  75.0,  300.0]   # O(C×K) × ~1 s/LLM call (Estimated)
    opt_e2e      = [12.0,  55.0,  210.0]   # batched + session cache (Derived)
    # Unbatched LLM calls
    legacy_llm   = [15,    75,    240]
    opt_llm      = [5,     15,    30]

    x = np.arange(len(scenarios))
    width = 0.20

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
    fig.patch.set_facecolor(COLORS["bg"])
    fig.suptitle("Figure 4: Legacy CLI vs. Optimized Flask/React — First-Stage Performance",
                 fontsize=12, fontweight="bold")

    # -- left: end-to-end latency --
    b1 = ax1.bar(x - width / 2, legacy_e2e, width, label="Legacy CLI",
                 color=COLORS["legacy"], alpha=0.85, edgecolor="white")
    b2 = ax1.bar(x + width / 2, opt_e2e,   width, label="Opt. Flask/React",
                 color=COLORS["flask"],  alpha=0.85, edgecolor="white")

    # Confidence tags
    tags = ["Estimated", "Estimated", "Estimated"]
    for rect, tag in zip(b1, tags):
        ax1.text(rect.get_x() + rect.get_width() / 2,
                 rect.get_height() + 4, tag,
                 ha="center", fontsize=6.5, color=COLORS["legacy"], style="italic")
    tags2 = ["Derived", "Derived", "Derived"]
    for rect, tag in zip(b2, tags2):
        ax1.text(rect.get_x() + rect.get_width() / 2,
                 rect.get_height() + 4, tag,
                 ha="center", fontsize=6.5, color=COLORS["flask"], style="italic")

    ax1.set_xticks(x)
    ax1.set_xticklabels(scenarios)
    ax1.set_ylabel("End-to-End Latency (s)")
    ax1.set_title("End-to-End Latency by Workload")
    ax1.legend()
    ax1.set_facecolor(COLORS["bg"])
    ax1.spines[["top", "right"]].set_visible(False)

    # -- right: LLM call count --
    b3 = ax2.bar(x - width / 2, legacy_llm, width, label="Legacy CLI  O(C×K)",
                 color=COLORS["legacy"], alpha=0.85, edgecolor="white")
    b4 = ax2.bar(x + width / 2, opt_llm,   width, label="Opt. Flask/React",
                 color=COLORS["flask"],  alpha=0.85, edgecolor="white")

    for rect in b3:
        ax2.text(rect.get_x() + rect.get_width() / 2,
                 rect.get_height() + 1, "Assumed",
                 ha="center", fontsize=6.5, color=COLORS["legacy"], style="italic")
    for rect in b4:
        ax2.text(rect.get_x() + rect.get_width() / 2,
                 rect.get_height() + 1, "Derived",
                 ha="center", fontsize=6.5, color=COLORS["flask"], style="italic")

    ax2.set_xticks(x)
    ax2.set_xticklabels(scenarios)
    ax2.set_ylabel("Unbatched LLM Calls (#)")
    ax2.set_title("LLM Call Count  O(C × K)")
    ax2.legend()
    ax2.set_facecolor(COLORS["bg"])
    ax2.spines[["top", "right"]].set_visible(False)

    fig.tight_layout()
    path = OUT_DIR / "fig4_first_stage_benchmark.png"
    fig.savefig(path, **SAVE_KW)
    plt.close(fig)
    print(f"  ✓  {path.name}")


# ═══════════════════════════════════════════════════════════════════════════════
# Figure 5 — Measured Neo4j Pipeline Per-Stage Latency (log scale)
# ═══════════════════════════════════════════════════════════════════════════════
def fig5_neo4j_latency_profile():
    # Data sourced from Table V of the paper (all values converted to seconds)
    stages = [
        # (label, layer, p50_s, p95_s)
        ("llm_classification\n_request",    "LLM Classification",     147.15,  197.66),
        ("llm_classification\n_task",        "LLM Classification",     147.50,  198.91),
        ("document_parsing",                 "Ingestion & Embedding",    9.89,   15.51),
        ("policy_embedding",                 "Ingestion & Embedding",   52.40,   52.40),
        ("upload_embedding",                 "Ingestion & Embedding",   69.94,   69.94),
        ("neo4j_node_writes",                "Neo4j Operations",         1.16,    1.69),
        ("neo4j_session_clear",              "Neo4j Operations",         1.13,    1.13),
        ("neo4j_compliance\n_edge_writes",   "Neo4j Operations",         0.03326, 0.79818),
        ("neo4j_direct_read",                "Neo4j Operations",         0.00760, 0.72840),
        ("neo4j_multi_hop_read",             "Neo4j Operations",         0.00644, 0.68189),
        ("faiss_search",                     "Retrieval",                6.727e-4,9.751e-4),
        ("faiss_index_build",                "Retrieval",                1.62e-3, 1.62e-3),
    ]

    layer_colors = {
        "LLM Classification":    COLORS["llm"],
        "Ingestion & Embedding": COLORS["flask"],
        "Neo4j Operations":      COLORS["neo4j"],
        "Retrieval":             COLORS["faiss"],
    }

    labels  = [s[0] for s in stages]
    layers  = [s[1] for s in stages]
    p50_vals = np.array([s[2] for s in stages])
    p95_vals = np.array([s[3] for s in stages])

    x = np.arange(len(stages))
    width = 0.35

    fig, ax = plt.subplots(figsize=(16, 6.5))
    fig.patch.set_facecolor(COLORS["bg"])
    ax.set_facecolor(COLORS["bg"])

    bar_colors = [layer_colors[l] for l in layers]

    bars_p50 = ax.bar(x - width / 2, p50_vals, width, label="p50 (median)",
                      color=[c + "bb" for c in bar_colors], edgecolor="white", linewidth=0.8)
    bars_p95 = ax.bar(x + width / 2, p95_vals, width, label="p95",
                      color=bar_colors, edgecolor="white", linewidth=0.8)

    ax.set_yscale("log")
    ax.set_ylabel("Latency (seconds, log scale)", fontsize=10)
    ax.set_title("Figure 5: Measured Neo4j Pipeline Per-Stage Latency (p50 vs p95)",
                 fontsize=12, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)

    # Layer legend patches
    layer_patches = [mpatches.Patch(color=c, label=l)
                     for l, c in layer_colors.items()]
    metric_patches = [
        mpatches.Patch(color="#aaa", label="p50 (median)", alpha=0.7),
        mpatches.Patch(color="#555", label="p95"),
    ]
    ax.legend(handles=layer_patches + metric_patches,
              loc="upper right", fontsize=8, ncol=2,
              framealpha=0.9)

    # Horizontal reference lines
    for y_ref, lbl in [(1.0, "1 s"), (0.001, "1 ms"), (1e-6, "1 µs")]:
        ax.axhline(y_ref, color="#ccc", linewidth=0.8, linestyle="--")
        ax.text(len(stages) - 0.3, y_ref * 1.3, lbl,
                fontsize=7.5, color="#999", va="bottom")

    fig.tight_layout()
    path = OUT_DIR / "fig5_neo4j_latency_profile.png"
    fig.savefig(path, **SAVE_KW)
    plt.close(fig)
    print(f"  ✓  {path.name}")


# ═══════════════════════════════════════════════════════════════════════════════
# Figure 6 — Example Multi-Hop Impact Subgraph
# ═══════════════════════════════════════════════════════════════════════════════
def fig6_multihop_subgraph():
    if not HAS_NX:
        print("  ⚠  networkx not installed — skipping Figure 6")
        return

    fig, (ax_graph, ax_cypher) = plt.subplots(1, 2, figsize=(16, 7),
                                               gridspec_kw={"width_ratios": [2, 1]})
    fig.patch.set_facecolor(COLORS["bg"])

    # ── Build a realistic sample subgraph ──────────────────────────────────
    # Uses clause IDs mirroring the IRDAI Health MC 2024 regulation
    G = nx.DiGraph()

    # PolicyClause nodes (p_<section>_<clause>)
    policy_nodes = [
        ("PC:§4.1 Waiting Period",     {"label": "PolicyClause", "hop": 0}),
        ("PC:§5.2 Pre-existing\nDisease",  {"label": "PolicyClause", "hop": 1}),
        ("PC:§6.1 Claim\nSettlement",  {"label": "PolicyClause", "hop": 1}),
        ("PC:§7.3 Cashless\nFacility", {"label": "PolicyClause", "hop": 2}),
        ("PC:§8.1 Exclusions",         {"label": "PolicyClause", "hop": 2}),
        ("PC:§9.4 Renewal\nTerms",     {"label": "PolicyClause", "hop": 3}),
    ]
    # RegulatoryClause nodes
    reg_nodes = [
        ("RC:IRDAI-MC-2024\n§3 (Waiting)", {"label": "RegulatoryClause"}),
        ("RC:IRDAI-MC-2024\n§11 (Claims)",  {"label": "RegulatoryClause"}),
    ]

    for n, d in policy_nodes + reg_nodes:
        G.add_node(n, **d)

    # DEPENDS_ON edges (policy ← policy)
    dep_edges = [
        ("PC:§4.1 Waiting Period",    "PC:§5.2 Pre-existing\nDisease"),
        ("PC:§4.1 Waiting Period",    "PC:§6.1 Claim\nSettlement"),
        ("PC:§5.2 Pre-existing\nDisease", "PC:§7.3 Cashless\nFacility"),
        ("PC:§6.1 Claim\nSettlement", "PC:§8.1 Exclusions"),
        ("PC:§7.3 Cashless\nFacility","PC:§9.4 Renewal\nTerms"),
    ]
    for u, v in dep_edges:
        G.add_edge(u, v, rel="DEPENDS_ON")

    # COMPLIANCE edges (reg → policy)
    comp_edges = [
        ("RC:IRDAI-MC-2024\n§3 (Waiting)", "PC:§4.1 Waiting Period",
         "CONFLICTS_WITH", {"reasoning": "36-month wait exceeds 48-month MC cap"}),
        ("RC:IRDAI-MC-2024\n§3 (Waiting)", "PC:§5.2 Pre-existing\nDisease",
         "COMPLIES_WITH",  {"reasoning": "PED wait period aligned with IRDAI mandate"}),
        ("RC:IRDAI-MC-2024\n§11 (Claims)",  "PC:§6.1 Claim\nSettlement",
         "CONFLICTS_WITH", {"reasoning": "Settlement window longer than MC §11.3 limit"}),
        ("RC:IRDAI-MC-2024\n§11 (Claims)",  "PC:§8.1 Exclusions",
         "SUPPORTS",       {"reasoning": "Exclusions list consistent with circular"}),
    ]
    for u, v, rel, props in comp_edges:
        G.add_edge(u, v, rel=rel, **props)

    # Layout — hierarchical left-to-right
    pos = {
        "PC:§4.1 Waiting Period":        (1.5, 3.5),
        "PC:§5.2 Pre-existing\nDisease":  (3.5, 4.5),
        "PC:§6.1 Claim\nSettlement":      (3.5, 2.5),
        "PC:§7.3 Cashless\nFacility":     (5.5, 5.0),
        "PC:§8.1 Exclusions":             (5.5, 2.0),
        "PC:§9.4 Renewal\nTerms":         (7.5, 5.0),
        "RC:IRDAI-MC-2024\n§3 (Waiting)": (0.0, 5.0),
        "RC:IRDAI-MC-2024\n§11 (Claims)":  (0.0, 2.0),
    }

    ax_graph.set_facecolor(COLORS["bg"])

    pol_nodes  = [n for n, d in G.nodes(data=True) if d.get("label") == "PolicyClause"]
    reg_nodes_ = [n for n, d in G.nodes(data=True) if d.get("label") == "RegulatoryClause"]
    dep_e      = [(u, v) for u, v, d in G.edges(data=True) if d.get("rel") == "DEPENDS_ON"]
    conf_e     = [(u, v) for u, v, d in G.edges(data=True) if d.get("rel") == "CONFLICTS_WITH"]
    comp_e     = [(u, v) for u, v, d in G.edges(data=True) if d.get("rel") == "COMPLIES_WITH"]
    supp_e     = [(u, v) for u, v, d in G.edges(data=True) if d.get("rel") == "SUPPORTS"]

    nx.draw_networkx_nodes(G, pos, nodelist=pol_nodes, ax=ax_graph,
                           node_color=COLORS["policy"], node_size=1800, node_shape="o")
    nx.draw_networkx_nodes(G, pos, nodelist=reg_nodes_, ax=ax_graph,
                           node_color=COLORS["reg"], node_size=2000, node_shape="s")
    nx.draw_networkx_labels(G, pos, ax=ax_graph, font_size=6.5,
                            font_color="white", font_weight="bold")

    arc = dict(connectionstyle="arc3,rad=0.12")
    nx.draw_networkx_edges(G, pos, edgelist=dep_e, ax=ax_graph,
                           edge_color=COLORS["neo4j"], width=2.0,
                           arrows=True, arrowsize=18,
                           connectionstyle="arc3,rad=0.0")
    nx.draw_networkx_edges(G, pos, edgelist=conf_e, ax=ax_graph,
                           edge_color=COLORS["legacy"], width=2.0,
                           style="dashed", arrows=True, arrowsize=18,
                           connectionstyle="arc3,rad=0.2")
    nx.draw_networkx_edges(G, pos, edgelist=comp_e, ax=ax_graph,
                           edge_color="#27ae60", width=2.0,
                           arrows=True, arrowsize=18,
                           connectionstyle="arc3,rad=0.2")
    nx.draw_networkx_edges(G, pos, edgelist=supp_e, ax=ax_graph,
                           edge_color="#f39c12", width=2.0,
                           arrows=True, arrowsize=18,
                           connectionstyle="arc3,rad=0.2")

    # Legend
    legend_handles = [
        mpatches.Patch(color=COLORS["policy"], label=":PolicyClause"),
        mpatches.Patch(color=COLORS["reg"],    label=":RegulatoryClause"),
        mpatches.Patch(color=COLORS["neo4j"],  label="DEPENDS_ON"),
        mpatches.Patch(color=COLORS["legacy"], label="CONFLICTS_WITH"),
        mpatches.Patch(color="#27ae60",         label="COMPLIES_WITH"),
        mpatches.Patch(color="#f39c12",         label="SUPPORTS"),
    ]
    ax_graph.legend(handles=legend_handles, loc="lower right",
                    fontsize=7.5, framealpha=0.9)
    ax_graph.set_title("Figure 6: Example Multi-Hop Impact Subgraph\n"
                        "(IRDAI Health MC 2024 → Sentra Policy Graph)",
                        fontsize=11, fontweight="bold")
    ax_graph.axis("off")

    # ── Cypher query callout ───────────────────────────────────────────────
    ax_cypher.set_facecolor("#1e1e2e")
    ax_cypher.axis("off")
    ax_cypher.set_title("Cypher Query\n(impact_analysis.py)",
                         fontsize=10, fontweight="bold", color="white",
                         pad=8)

    cypher = textwrap.dedent("""\
        // Direct compliance edges
        MATCH (r:RegulatoryClause {id: $rid,
               session_id: $sid})
              -[e:CONFLICTS_WITH|COMPLIES_WITH
               |SUPPORTS|IS_REDUNDANT]->
              (p:PolicyClause)
        RETURN p.id          AS policy_id,
               p.text        AS text,
               p.section     AS section,
               type(e)       AS relationship,
               e.classified_at,
               e.reasoning
        ORDER BY relationship, p.id;

        // Indirect impacts via DEPENDS_ON
        MATCH (direct:PolicyClause
               {session_id: $sid})
              -[:DEPENDS_ON*1..3]->
              (indirect:PolicyClause
               {session_id: $sid})
        WHERE direct.id IN $direct_ids
          AND indirect.id NOT IN $direct_ids
        RETURN DISTINCT
               indirect.id      AS policy_id,
               indirect.section AS section,
               indirect.text    AS text;
    """)

    ax_cypher.text(0.03, 0.97, cypher,
                   transform=ax_cypher.transAxes,
                   fontsize=7.5, va="top", ha="left",
                   color="#a6e3a1",
                   fontfamily="monospace",
                   linespacing=1.6)

    fig.tight_layout()
    path = OUT_DIR / "fig6_multihop_subgraph.png"
    fig.savefig(path, **SAVE_KW)
    plt.close(fig)
    print(f"  ✓  {path.name}")


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print(f"\nGenerating figures → {OUT_DIR}\n")
    fig1_architecture_evolution()
    fig2_neo4j_schema()
    fig3_graph_rag_flow()
    fig4_first_stage_benchmark()
    fig5_neo4j_latency_profile()
    fig6_multihop_subgraph()
    print(f"\nAll figures saved to: {OUT_DIR}\n")
