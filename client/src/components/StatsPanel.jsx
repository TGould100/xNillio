import { useState, useEffect } from 'react'
import './StatsPanel.css'

function StatsPanel({ stats, loading }) {
  const [graphStats, setGraphStats] = useState(null)
  const [loadingGraph, setLoadingGraph] = useState(false)

  useEffect(() => {
    // Load detailed graph stats
    setLoadingGraph(true)
    fetch('/api/stats/graph')
      .then(res => res.json())
      .then(data => {
        setGraphStats(data)
        setLoadingGraph(false)
      })
      .catch(err => {
        console.error('Failed to load graph stats:', err)
        setLoadingGraph(false)
      })
  }, [])

  return (
    <div className="stats-panel">
      <h2>Dictionary Statistics</h2>
      
      {loading || loadingGraph ? (
        <div className="stats-loading">Loading statistics...</div>
      ) : (
        <>
          {stats && (
            <div className="stat-section">
              <h3>Overview</h3>
              <div className="stat-item">
                <span className="stat-label">Total Words:</span>
                <span className="stat-value">{stats.total_words?.toLocaleString() || 'N/A'}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Avg Definition Length:</span>
                <span className="stat-value">{stats.average_definition_length || 'N/A'}</span>
              </div>
              {stats.average_degree_centrality !== undefined && (
                <div className="stat-item">
                  <span className="stat-label">Avg Degree Centrality:</span>
                  <span className="stat-value">{stats.average_degree_centrality.toFixed(2)}</span>
                </div>
              )}
            </div>
          )}
          
          {graphStats && !graphStats.error && (
            <>
              <div className="stat-section">
                <h3>Graph Structure</h3>
                <div className="stat-item">
                  <span className="stat-label">Nodes:</span>
                  <span className="stat-value">{graphStats.nodes?.toLocaleString() || 'N/A'}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Edges:</span>
                  <span className="stat-value">{graphStats.edges?.toLocaleString() || 'N/A'}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Avg In-Degree:</span>
                  <span className="stat-value">{graphStats.average_in_degree || 'N/A'}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Avg Out-Degree:</span>
                  <span className="stat-value">{graphStats.average_out_degree || 'N/A'}</span>
                </div>
              </div>
              
              {graphStats.cycle_count !== undefined && (
                <div className="stat-section">
                  <h3>Circular Dependencies</h3>
                  <div className="stat-item">
                    <span className="stat-label">Total Cycles:</span>
                    <span className="stat-value">{graphStats.cycle_count}</span>
                  </div>
                </div>
              )}
              
              {graphStats.top_words_by_in_degree && graphStats.top_words_by_in_degree.length > 0 && (
                <div className="stat-section">
                  <h3>Most Referenced Words</h3>
                  <div className="top-words-list">
                    {graphStats.top_words_by_in_degree.slice(0, 5).map((item, idx) => (
                      <div key={idx} className="top-word-item">
                        <span className="word-name">{item.word}</span>
                        <span className="word-count">{item.count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
          
          {graphStats?.error && (
            <div className="stats-error">
              {graphStats.error === "Graph is empty. Please load dictionary data first." 
                ? "Load dictionary data to see graph statistics"
                : "Unable to load graph statistics"}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default StatsPanel

