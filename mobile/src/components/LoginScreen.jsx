import { useState } from 'react'

export default function LoginScreen({ onLogin, busy, error }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  return <main className="auth-screen">
    <section className="auth-card">
      <div className="brand-mark">M</div>
      <h1>Munkalap</h1><p>Technikusi alkalmazás</p>
      <form onSubmit={e => { e.preventDefault(); onLogin(email.trim(), password) }}>
        <label>E-mail<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} /></label>
        <label>Jelszó<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
        {error && <div className="error-box">{error}</div>}
        <button className="btn primary" disabled={busy}>{busy ? 'Bejelentkezés…' : 'Bejelentkezés'}</button>
      </form>
    </section>
  </main>
}
