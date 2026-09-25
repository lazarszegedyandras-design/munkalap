import React, { useState } from 'react'

export default function Login({ onLogin, onMfaSetup, onMfaConfirm, onMfaVerify, onMfaSetupFinished }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [stage, setStage] = useState('credentials')
  const [challengeToken, setChallengeToken] = useState('')
  const [setup, setSetup] = useState(null)
  const [mfaCode, setMfaCode] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submitCredentials(event) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      const result = await onLogin(email, password)
      if (result?.mfa_setup_required) {
        setChallengeToken(result.challenge_token)
        const data = await onMfaSetup(result.challenge_token)
        setSetup(data)
        setStage('setup')
      } else if (result?.mfa_required) {
        setChallengeToken(result.challenge_token)
        setStage('verify')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function submitMfa(event) {
    event.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (stage === 'setup') {
        const result = await onMfaConfirm(challengeToken, mfaCode)
        setRecoveryCodes(result.recovery_codes || [])
        setStage('recovery')
      } else {
        await onMfaVerify(challengeToken, mfaCode)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (stage === 'recovery') {
    return (
      <div className="login-page">
        <div className="login-card">
          <h1>MFA helyreállító kódok</h1>
          <p>Másold el és tárold biztonságos helyen. Minden kód egyszer használható.</p>
          <pre className="mfa-recovery-codes">{recoveryCodes.join('\n')}</pre>
          <button onClick={() => onMfaSetupFinished()} disabled={loading}>Elmentettem, folytatás</button>
        </div>
      </div>
    )
  }

  if (stage === 'setup') {
    return (
      <div className="login-page">
        <form className="login-card" onSubmit={submitMfa}>
          <h1>Kétlépcsős azonosítás beállítása</h1>
          <p>Add hozzá ezt a kulcsot Microsoft Authenticatorhoz, Google Authenticatorhoz vagy más TOTP alkalmazáshoz.</p>
          <label>Beállítási kulcs<input value={setup?.secret || ''} readOnly /></label>
          <details>
            <summary>Technikai URI</summary>
            <code className="mfa-uri">{setup?.otpauth_uri}</code>
          </details>
          <label>6 jegyű ellenőrző kód<input inputMode="numeric" autoComplete="one-time-code" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} required /></label>
          {error && <div className="error">{error}</div>}
          <button disabled={loading}>{loading ? 'Ellenőrzés...' : 'MFA aktiválása'}</button>
        </form>
      </div>
    )
  }

  if (stage === 'verify') {
    return (
      <div className="login-page">
        <form className="login-card" onSubmit={submitMfa}>
          <h1>Kétlépcsős azonosítás</h1>
          <p>Írd be az authenticator alkalmazás 6 jegyű kódját, vagy egy helyreállító kódot.</p>
          <label>MFA / helyreállító kód<input autoFocus autoComplete="one-time-code" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} required /></label>
          {error && <div className="error">{error}</div>}
          <button disabled={loading}>{loading ? 'Ellenőrzés...' : 'Belépés'}</button>
        </form>
      </div>
    )
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submitCredentials}>
        <h1>Munkalap és eszköznyilvántartó</h1>
        <label>Email<input name="username" value={email} onChange={(e) => setEmail(e.target.value)} type="email" autoComplete="username" required /></label>
        <label>Jelszó<input name="password" value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" required /></label>
        {error && <div className="error">{error}</div>}
        <button disabled={loading}>{loading ? 'Belépés...' : 'Belépés'}</button>
      </form>
    </div>
  )
}
