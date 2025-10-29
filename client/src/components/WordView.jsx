import { useState, useEffect } from 'react'
import React from 'react'
import './WordView.css'

function WordView({ word, onWordClick }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    
    fetch(`/api/words/${encodeURIComponent(word)}`)
      .then(res => {
        if (!res.ok) {
          if (res.status === 404) {
            throw new Error(`Word "${word}" not found in dictionary`)
          }
          throw new Error('Failed to fetch word')
        }
        return res.json()
      })
      .then(data => {
        setData(data)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [word])

  const renderDefinition = (text, linkedWords) => {
    if (!text) return null
    
    // Split by word boundaries to preserve spaces and punctuation
    const parts = []
    let lastIndex = 0
    
    // Create a regex that finds word boundaries
    const wordRegex = /\b\w+\b/g
    let match
    
    while ((match = wordRegex.exec(text)) !== null) {
      // Add text before the word (preserves spaces and punctuation)
      if (match.index > lastIndex) {
        const before = text.substring(lastIndex, match.index)
        parts.push({ type: 'text', content: before })
      }
      
      // Add the word itself
      const word = match[0]
      const lowerWord = word.toLowerCase()
      
      if (linkedWords.includes(lowerWord)) {
        parts.push({
          type: 'link',
          content: word,
          word: lowerWord
        })
      } else {
        parts.push({ type: 'text', content: word })
      }
      
      lastIndex = match.index + word.length
    }
    
    // Add remaining text after last word
    if (lastIndex < text.length) {
      parts.push({ type: 'text', content: text.substring(lastIndex) })
    }
    
    // Render the parts, ensuring spacing is preserved around links
    // Combine adjacent text parts and render as string to preserve all whitespace
    const result = []
    let currentText = ''
    
    parts.forEach((part, idx) => {
      if (part.type === 'link') {
        // If we have accumulated text, render it first
        if (currentText) {
          result.push(
            <span key={`text-before-${idx}`}>{currentText}</span>
          )
          currentText = ''
        }
        // Render the link button
        result.push(
          <button
            key={`link-${idx}`}
            className="word-link"
            style={{ display: 'inline' }}
            onClick={(e) => {
              e.preventDefault()
              onWordClick(part.word)
            }}
            title={`Click to see definition of "${part.word}"`}
          >
            {part.content}
          </button>
        )
      } else {
        // Accumulate text parts to preserve whitespace between them
        currentText += part.content
      }
    })
    
    // Render any remaining accumulated text
    if (currentText) {
      result.push(
        <span key="text-final">{currentText}</span>
      )
    }
    
    return result
  }

  if (loading) {
    return (
      <div className="word-view loading">
        <div className="spinner"></div>
        <p>Loading definition for "{word}"...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="word-view error">
        <h2>{error}</h2>
        <p>Try searching for a different word.</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="word-view error">
        <h2>No data available</h2>
      </div>
    )
  }

  return (
    <div className="word-view">
      <div className="word-header">
        <div className="word-title-container">
          <h1 className="word-title">{data.word}</h1>
          {data.pronunciation && (
            <span className="pronunciation">/{data.pronunciation}/</span>
          )}
        </div>
        {data.linked_words && data.linked_words.length > 0 && (
          <div className="linked-words-count">
            {data.linked_words.length} linked word{data.linked_words.length !== 1 ? 's' : ''}
          </div>
        )}
      </div>
      
      <div className="definition-container">
        <div className="definition">
          {renderDefinition(data.definition, data.linked_words || [])}
        </div>
      </div>
      
      {data.linked_words && data.linked_words.length > 0 && (
        <div className="linked-words-section">
          <h3>Linked Words</h3>
          <div className="linked-words-list">
            {data.linked_words.map((linkedWord, idx) => (
              <button
                key={idx}
                className="linked-word-tag"
                onClick={() => onWordClick(linkedWord)}
              >
                {linkedWord}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default WordView

