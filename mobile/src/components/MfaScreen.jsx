import { useState } from 'react'
export default function MfaScreen({ onVerify, onCancel, busy, error }) {
  const [code, setCode] = useState('')
  return <main className="auth-screen"><section className="auth-card">
    <h1>Kétlépcsős azonosítás</h1>
    <p>Add meg az authenticator alkalmazás 6 jegyű kódját vagy egy recovery kódot.</p>
    <form onSubmit={e => { e.preventDefault(); onVerify(code.trim()) }}>
      <label>Biztonsági kód<input inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={e => setCode(e.target.value)} /></label>
      {error && <div className="error-box">{error}</div>}
      <button className="btn primary" disabled={busy}>Ellenőrzés</button>
      <button type="button" className="btn secondary" onClick={onCancel}>Vissza</button>
    </form>
  </section></main>
}
