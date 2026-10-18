from reasoning.graph_store import driver

with driver.session() as session:
    res = session.run("MATCH (n) RETURN DISTINCT n.session_id as sid, count(n) as count ORDER BY count DESC LIMIT 10").data()
    print("Recent sessions:")
    for r in res:
        sid = r["sid"]
        node_types = session.run("MATCH (n {session_id: $s}) RETURN labels(n)[0] as lbl, count(n) as count", s=sid).data()
        edges = session.run("MATCH (n {session_id: $s})-[e]->(m {session_id: $s}) RETURN type(e) as rel, count(e) as count", s=sid).data()
        print(f"Session {sid}: nodes = {node_types}, edges = {edges}")
