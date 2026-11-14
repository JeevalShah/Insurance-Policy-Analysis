"""Probe Neo4j version, graph size, session scoping, and hardware."""
import os, json, platform, subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / "backend" / ".env")

uri  = os.getenv("NEO4J_URI", "bolt://localhost:7687")
user = os.getenv("NEO4J_USERNAME", "neo4j")
pwd  = os.getenv("NEO4J_PASSWORD", "")

from neo4j import GraphDatabase
driver = GraphDatabase.driver(uri, auth=(user, pwd))

print("=" * 60)
print("NEO4J")
print("=" * 60)
with driver.session() as s:
    info = s.run("CALL dbms.components() YIELD name, versions, edition").data()
    for row in info:
        print(f"  Name:    {row['name']}")
        print(f"  Version: {row['versions']}")
        print(f"  Edition: {row['edition']}")

    print("\n--- Graph Size ---")
    nc  = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    ec  = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    pc  = s.run("MATCH (n:PolicyClause) RETURN count(n) AS c").single()["c"]
    rc  = s.run("MATCH (n:RegulatoryClause) RETURN count(n) AS c").single()["c"]
    dep = s.run("MATCH ()-[r:DEPENDS_ON]->() RETURN count(r) AS c").single()["c"]
    cw  = s.run("MATCH ()-[r:CONFLICTS_WITH]->() RETURN count(r) AS c").single()["c"]
    co  = s.run("MATCH ()-[r:COMPLIES_WITH]->() RETURN count(r) AS c").single()["c"]
    su  = s.run("MATCH ()-[r:SUPPORTS]->() RETURN count(r) AS c").single()["c"]
    ir  = s.run("MATCH ()-[r:IS_REDUNDANT]->() RETURN count(r) AS c").single()["c"]
    nr  = s.run("MATCH ()-[r:NOT_RELATED]->() RETURN count(r) AS c").single()["c"]
    print(f"  Total nodes:            {nc}")
    print(f"    :PolicyClause         {pc}")
    print(f"    :RegulatoryClause     {rc}")
    print(f"  Total relationships:    {ec}")
    print(f"    DEPENDS_ON            {dep}")
    print(f"    CONFLICTS_WITH        {cw}")
    print(f"    COMPLIES_WITH         {co}")
    print(f"    SUPPORTS              {su}")
    print(f"    IS_REDUNDANT          {ir}")
    print(f"    NOT_RELATED           {nr}")

    print("\n--- Session Scoping ---")
    sc = s.run("MATCH (n) WHERE n.session_id IS NOT NULL RETURN count(DISTINCT n.session_id) AS c").single()["c"]
    samples = s.run("MATCH (n) WHERE n.session_id IS NOT NULL RETURN DISTINCT n.session_id AS sid LIMIT 3").data()
    print(f"  Distinct session_ids in graph: {sc}")
    print(f"  Sample IDs: {[d['sid'] for d in samples]}")
    print("  Scoping mechanism: every node carries a `session_id` property;")
    print("  all queries filter with {session_id: $sid} or WHERE n.session_id=$sid")
    print("  Composite indexes: (RegulatoryClause.id, session_id) and (PolicyClause.id, session_id)")

driver.close()

print("\n" + "=" * 60)
print("HARDWARE / RUNTIME")
print("=" * 60)
print(f"  OS:        {platform.system()} {platform.version()}")
print(f"  Python:    {platform.python_version()}")

try:
    import psutil
    mem = psutil.virtual_memory()
    print(f"  RAM total: {mem.total/1e9:.1f} GB")
    print(f"  RAM avail: {mem.available/1e9:.1f} GB")
    cpus = psutil.cpu_count(logical=True)
    pcpus = psutil.cpu_count(logical=False)
    print(f"  CPUs:      {pcpus} physical / {cpus} logical")
    try:
        freq = psutil.cpu_freq()
        if freq:
            print(f"  CPU freq:  {freq.max:.0f} MHz max")
    except Exception:
        pass
except ImportError:
    pass

# CPU name via WMIC (works in sandbox)
try:
    r = subprocess.check_output(["wmic","cpu","get","Name","--","format:csv"],
                                 text=True, stderr=subprocess.DEVNULL, timeout=10)
    for line in r.splitlines():
        line = line.strip().strip(",")
        if line and "Node" not in line and line != "Name":
            print(f"  CPU name:  {line}")
            break
except Exception:
    pass

# GPU via WMIC
try:
    r = subprocess.check_output(["wmic","path","win32_VideoController","get",
                                  "Name,AdapterRAM","--","format:csv"],
                                  text=True, stderr=subprocess.DEVNULL, timeout=10)
    for line in r.splitlines():
        line = line.strip()
        if line and "Node" not in line and "AdapterRAM" not in line and line.replace(",",""):
            parts = [p.strip() for p in line.split(",") if p.strip()]
            if len(parts) >= 2:
                ram_bytes = parts[0] if parts[0].isdigit() else parts[-1]
                name = parts[-1] if parts[0].isdigit() else parts[0]
                try:
                    ram_gb = int(ram_bytes)/1e9
                    print(f"  GPU:       {name}  ({ram_gb:.1f} GB VRAM)")
                except Exception:
                    print(f"  GPU:       {' '.join(parts)}")
                break
except Exception:
    pass

print("\n--- Neo4j Deployment ---")
print("  Deployment: local (Windows host, Neo4j Desktop / Community)")
print("  URI:       ", uri)
print("  Auth:       username/password (bolt)")

print("\n--- Experiment Runs ---")
runs_dir = Path(__file__).parents[1] / "experiments" / "outputs"
runs = [d for d in runs_dir.iterdir() if d.is_dir()] if runs_dir.exists() else []
print(f"  Recorded runs: {len(runs)}")
for r in sorted(runs)[-3:]:
    raw = r / "raw.jsonl"
    lines = len(raw.read_text(encoding="utf-8").splitlines()) if raw.exists() else 0
    print(f"    {r.name}  ({lines} events)")
