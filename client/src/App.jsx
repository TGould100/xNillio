import { useState, useEffect } from 'react'
import { BrowserRouter as Router, Routes, Route, useNavigate, useParams } from 'react-router-dom'
import SearchBar from './components/SearchBar'
import WordView from './components/WordView'
import StatsPanel from './components/StatsPanel'
import './App.css'

function AppContent() {
  const [stats, setStats] = useState(null)
  const [loadingStats, setLoadingStats] = useState(true)

  useEffect(() => {
    fetch('/api/stats/overview')
      .then(res => res.json())
      .then(data => {
        setStats(data)
        setLoadingStats(false)
      })
      .catch(err => {
        console.error('Failed to load stats:', err)
        setLoadingStats(false)
      })
  }, [])

  return (
    <div className="app">
      <header className="app-header">
        <h1>GCIDE Dictionary Explorer</h1>
        <p className="subtitle">Explore the fascinating web of word relationships</p>
      </header>
      
      <div className="app-content">
        <div className="main-panel">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/word/:word" element={<WordPage />} />
          </Routes>
        </div>
        
        <aside className="sidebar">
          <StatsPanel stats={stats} loading={loadingStats} />
        </aside>
      </div>
    </div>
  )
}

function HomePage() {
  const navigate = useNavigate()
  
  return (
    <div className="home-page">
      <SearchBar onSearch={(word) => navigate(`/word/${encodeURIComponent(word)}`)} />
      <div className="welcome-message">
        <h2>Welcome to the GCIDE Dictionary Explorer</h2>
        <p>
          Enter a word above to see its definition. Words in definitions are clickable links,
          allowing you to explore the interconnected web of language.
        </p>
      </div>
    </div>
  )
}

function WordPage() {
  const { word } = useParams()
  const navigate = useNavigate()
  
  return (
    <div className="word-page">
      <SearchBar 
        initialValue={word} 
        onSearch={(newWord) => navigate(`/word/${encodeURIComponent(newWord)}`)} 
      />
      <WordView 
        word={decodeURIComponent(word)} 
        onWordClick={(clickedWord) => navigate(`/word/${encodeURIComponent(clickedWord)}`)}
      />
    </div>
  )
}

function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  )
}

export default App

