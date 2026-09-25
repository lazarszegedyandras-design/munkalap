import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import './styles/app.css'

const rootElement = document.getElementById('root')
const fallback = document.getElementById('boot-fallback')

function hideBootFallback() {
  if (fallback) fallback.style.display = 'none'
}

try {
  createRoot(rootElement).render(
    <React.StrictMode>
      <ErrorBoundary>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ErrorBoundary>
    </React.StrictMode>,
  )
  hideBootFallback()
} catch (error) {
  console.error('Frontend boot error:', error)
  if (fallback) {
    fallback.innerHTML = `
      <div class="fatal-error">
        <h1>Az alkalmazás nem tudott elindulni</h1>
        <p>A frontend fájlok betöltődtek, de a React indítás közben hibára futott.</p>
        <pre>${String(error?.message || error)}</pre>
      </div>
    `
  }
}
