import React, { useEffect, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import axios from 'axios';

export default function GraphVisualizer({ sessionId }) {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchGraph() {
      try {
        const { data } = await axios.get(`/api/graph/${sessionId}`);
        setGraphData(data);
      } catch (err) {
        console.error("Failed to load graph data", err);
      } finally {
        setLoading(false);
      }
    }
    if (sessionId) fetchGraph();
  }, [sessionId]);

  if (loading) return <div className="empty-state"><span className="spinner" />Loading Graph...</div>;
  if (!graphData.nodes.length) return null;

  return (
    <section className="graph-panel" style={{ marginTop: '48px', borderTop: '2px solid var(--ink)', paddingTop: '28px' }}>
      <span className="eyebrow">Interactive</span>
      <h1 className="page-title">Dependency & Compliance Graph</h1>
      <p className="page-lede">Visualizing regulatory triggers and downstream indirect impacts.</p>
      
      <div style={{ height: '500px', border: '1px solid var(--line)', borderRadius: '3px', backgroundColor: '#fff' }}>
        <ForceGraph2D
          graphData={graphData}
          nodeAutoColorBy="group"
          nodeLabel="label"
          linkDirectionalArrowLength={3.5}
          linkDirectionalArrowRelPos={1}
          linkColor="color"
          linkLabel="label"
        />
      </div>
    </section>
  );
}