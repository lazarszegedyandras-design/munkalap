import React from 'react'
import { csrfHeaders, exportUrl } from '../api.js'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Frontend render error:', error, info)
  }

  async clearSession() {
    try {
      await fetch(exportUrl('/auth/logout'), {
        method: 'POST',
        credentials: 'include',
        headers: csrfHeaders(),
      })
    } catch {
      // A helyi újratöltést akkor sem blokkoljuk, ha a backend nem elérhető.
    }
    localStorage.removeItem('token')
    window.location.href = '/'
  }

  render() {
    if (this.state.error) {
      return (
        <div className="fatal-error">
          <h1>Az alkalmazás nem tudott betölteni</h1>
          <p>A frontend fut, de a böngészőoldali React alkalmazás hibára futott.</p>
          <pre>{this.state.error.message}</pre>
          <button onClick={() => this.clearSession()}>
            Munkamenet törlése és újratöltés
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
