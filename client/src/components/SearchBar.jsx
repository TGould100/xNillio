import { useState, useEffect } from 'react'
import './SearchBar.css'

function SearchBar({ onSearch, initialValue = '' }) {
  const [query, setQuery] = useState(initialValue)
  const [suggestions, setSuggestions] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)

  useEffect(() => {
    setQuery(initialValue)
  }, [initialValue])

  const handleInputChange = (e) => {
    const value = e.target.value
    setQuery(value)
    
    if (value.length > 1) {
      fetch(`/api/words/search/${encodeURIComponent(value)}?limit=5`)
        .then(res => res.json())
        .then(data => {
          setSuggestions(data.results || [])
          setShowSuggestions(true)
        })
        .catch(() => setSuggestions([]))
    } else {
      setSuggestions([])
      setShowSuggestions(false)
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (query.trim()) {
      onSearch(query.trim())
      setShowSuggestions(false)
    }
  }

  const handleSuggestionClick = (suggestion) => {
    setQuery(suggestion)
    onSearch(suggestion)
    setShowSuggestions(false)
  }

  return (
    <div className="search-bar-container">
      <form onSubmit={handleSubmit} className="search-form">
        <input
          type="text"
          value={query}
          onChange={handleInputChange}
          placeholder="Enter a word to explore..."
          className="search-input"
          autoFocus
        />
        <button type="submit" className="search-button">
          Search
        </button>
      </form>
      
      {showSuggestions && suggestions.length > 0 && (
        <div className="suggestions-dropdown">
          {suggestions.map((suggestion, idx) => (
            <div
              key={idx}
              className="suggestion-item"
              onClick={() => handleSuggestionClick(suggestion)}
            >
              {suggestion}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default SearchBar

