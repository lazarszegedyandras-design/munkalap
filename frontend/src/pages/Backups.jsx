import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api.js'
import { Field } from '../components/FormField.jsx'
import { hasPermission } from '../utils/permissions.js'
import { useSecurityStepUp } from '../components/SecurityStepUpModal.jsx'

function formatBytes(value) {
  const bytes = Number(value || 0)
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = bytes
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1 }
  return `${size >= 10 || unit === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`
}

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('hu-HU')
}

function jobKind(row) {
  if (row.effective_kind === 'master') return 'MASTER'
  if (row.effective_kind === 'incremental') return 'INCREMENTÁLIS'
  if (row.requested_kind === 'master') return 'MASTER (várakozik)'
  return 'INKREMENTÁLIS (várakozik)'
}

function triggerLabel(value) {
  return ({
    manual: 'Manuális',
    scheduled: 'Automatikus',
    pre_restore: 'Pre-restore',
    post_restore: 'Post-restore',
    rollback_restore: 'Rollback MASTER',
  })[value] || value
}

function statusLabel(value) {
  return ({
    queued: 'Várakozik',
    running: 'Folyamatban',
    success: 'Sikeres',
    failed: 'Sikertelen',
    interrupted: 'Megszakadt',
    critical: 'Kritikus hiba',
  })[value] || value
}

export default function Backups({ user }) {
  const { runSensitive, stepUpModal } = useSecurityStepUp()
  const canRestore = hasPermission(user, 'admin.backup.restore')
  const [status, setStatus] = useState(null)
  const [jobs, setJobs] = useState([])
  const [restores, setRestores] = useState([])
  const [schedule, setSchedule] = useState({ enabled: false, daily_time: '23:30', timezone: 'Europe/Budapest' })
  const [restoreBackupId, setRestoreBackupId] = useState('')
  const [restoreConfirmation, setRestoreConfirmation] = useState('')
  const [recoveryConfirmation, setRecoveryConfirmation] = useState('')
  const restoreRequestedRef = useRef(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [restoring, setRestoring] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const runningJob = useMemo(() => jobs.find((row) => row.status === 'running' || row.status === 'queued'), [jobs])
  const runningRestore = useMemo(() => restores.find((row) => row.status === 'running' || row.status === 'queued'), [restores])
  const busy = Boolean(runningJob || runningRestore || status?.job_running || status?.restore_running)
  const successfulBackups = useMemo(() => jobs.filter((row) => row.status === 'success'), [jobs])
  const compatibleBackups = useMemo(
    () => successfulBackups.filter((row) => status?.deployment_fingerprint && row.deployment_fingerprint === status.deployment_fingerprint),
    [successfulBackups, status?.deployment_fingerprint],
  )

  async function load({ quiet = false, syncSchedule = false } = {}) {
    if (!quiet) setLoading(true)
    try {
      const requests = [api('/backups/status'), api('/backups?limit=100')]
      if (canRestore) requests.push(api('/backups/restores?limit=50'))
      const [state, list, restoreList = []] = await Promise.all(requests)
      setStatus(state)
      setJobs(list)
      setRestores(restoreList)
      if (syncSchedule && state.schedule) setSchedule(state.schedule)
      const compatible = list.filter(
        (row) => row.status === 'success' && state?.deployment_fingerprint && row.deployment_fingerprint === state.deployment_fingerprint,
      )
      setRestoreBackupId((current) => (
        current && compatible.some((row) => row.id === current) ? current : (compatible[0]?.id || '')
      ))
      const restoreActive = Boolean(state?.restore_running)
      restoreRequestedRef.current = restoreActive
      setError('')
    } catch (err) {
      if (restoreRequestedRef.current) {
        setMessage('A visszaállítás közben az alkalmazás rövid időre leáll. A kapcsolat helyreállása után az állapot automatikusan frissül.')
      } else {
        setError(err.message)
      }
    } finally {
      if (!quiet) setLoading(false)
    }
  }

  useEffect(() => {
    load({ syncSchedule: true })
    const timer = window.setInterval(() => load({ quiet: true }), 5000)
    return () => window.clearInterval(timer)
  }, [canRestore])

  async function saveSchedule(e) {
    e.preventDefault()
    setSaving(true); setError(''); setMessage('')
    try {
      const updated = await api('/backups/schedule', { method: 'PUT', body: schedule })
      setSchedule(updated)
      setMessage('Az automatikus mentési ütemezés elmentve.')
      await load({ quiet: true })
    } catch (err) { setError(err.message) }
    finally { setSaving(false) }
  }

  async function createMaster() {
    if (!window.confirm('Elindítod a teljes MASTER mentést? A művelet nagyobb tárhelyet és több időt igényelhet.')) return
    setError(''); setMessage('')
    try {
      const result = await api('/backups/master', { method: 'POST' })
      setMessage(`MASTER mentés elindítva: ${result.job_id}`)
      await load({ quiet: true })
    } catch (err) { setError(err.message) }
  }

  async function validate(row) {
    setError(''); setMessage('')
    try {
      const result = await api(`/backups/${row.id}/validate`, { method: 'POST' })
      setMessage(`${result.backup_id}: integritásellenőrzés sikeres (${result.chain_points || 1} mentési pont, ${result.checked_files} fájl, pgBackRest repository ellenőrizve).`)
    } catch (err) { setError(err.message) }
  }

  async function clearRecoveryLock() {
    if (recoveryConfirmation !== 'HELYREALLITAS_KESZ') {
      setError('A zárolás feloldásához pontosan ezt kell beírni: HELYREALLITAS_KESZ')
      return
    }
    if (!window.confirm('Csak akkor oldd fel a zárolást, ha a host-szintű helyreállítás és az adatbázis/alkalmazás ellenőrzése már megtörtént. Folytatod?')) return
    setError(''); setMessage('')
    try {
      await runSensitive(() => api('/backups/recovery/clear', { method: 'POST', body: { confirmation: recoveryConfirmation } }))
      setRecoveryConfirmation('')
      setMessage('A restore biztonsági zárolás feloldva.')
      await load({ quiet: true })
    } catch (err) { setError(err.message) }
  }

  async function restoreSelected(event) {
    event.preventDefault()
    if (!restoreBackupId) {
      setError('Válassz visszaállítási pontot.')
      return
    }
    if (restoreConfirmation !== 'VISSZAALLIT') {
      setError('A visszaállításhoz pontosan ezt kell beírni: VISSZAALLIT')
      return
    }
    if (!window.confirm(`Biztosan visszaállítod a rendszert erre a mentési pontra?\n${restoreBackupId}\n\nA rendszer előtte automatikus pre-restore MASTER mentést készít.`)) return
    setRestoring(true); setError(''); setMessage('')
    try {
      const result = await runSensitive(() => api(`/backups/${encodeURIComponent(restoreBackupId)}/restore`, {
        method: 'POST',
        body: { confirmation: restoreConfirmation },
      }))
      restoreRequestedRef.current = true
      setRestoreConfirmation('')
      setMessage(`Visszaállítás elindítva: ${result.restore_id}. Az alkalmazás a folyamat közben átmenetileg elérhetetlenné válhat.`)
      await load({ quiet: true })
    } catch (err) { setError(err.message) }
    finally { setRestoring(false) }
  }

  if (loading) return <section><h1>Biztonsági mentések</h1><div className="panel">Betöltés...</div></section>

  return (
    <section className="backup-page">
      {stepUpModal}
      <div className="page-head">
        <div>
          <h1>Biztonsági mentések</h1>
          <p className="muted">Rendszerszintű MASTER és inkrementális mentések, napi ütemezéssel. A hónap utolsó napján automatikusan MASTER készül.</p>
        </div>
        <div className="inline-actions">
          <button type="button" onClick={createMaster} disabled={Boolean(busy || status?.restore_recovery_required)}>MASTER mentés készítése most</button>
          <button type="button" className="secondary" onClick={() => load()}>Frissítés</button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {message && <div className="success">{message}</div>}
      {status?.restore_recovery_required && (
        <div className="warning-box">
          <p>A backup-agent egy korábbi restore megszakadását észlelte. Új mentés vagy webes visszaállítás nem indítható, amíg a host-szintű helyreállítás és ellenőrzés meg nem történt.</p>
          {canRestore && (
            <div className="inline-actions">
              <input value={recoveryConfirmation} onChange={(e) => setRecoveryConfirmation(e.target.value)} placeholder="HELYREALLITAS_KESZ" autoComplete="off" />
              <button type="button" className="danger" disabled={recoveryConfirmation !== 'HELYREALLITAS_KESZ'} onClick={clearRecoveryLock}>Zárolás feloldása</button>
            </div>
          )}
        </div>
      )}

      <div className="backup-status-grid">
        <div className="metric"><span>Legutóbbi sikeres mentés</span><strong>{status?.latest_backup?.id || '—'}</strong><small>{formatDate(status?.latest_backup?.finished_at)}</small></div>
        <div className="metric"><span>Legutóbbi MASTER</span><strong>{status?.latest_master?.id || '—'}</strong><small>{formatDate(status?.latest_master?.finished_at)}</small></div>
        <div className="metric"><span>Repository szabad hely</span><strong>{formatBytes(status?.repository?.free_bytes)}</strong><small>Összesen: {formatBytes(status?.repository?.total_bytes)}</small></div>
        <div className="metric"><span>Backup-agent</span><strong>{busy ? 'Foglalt' : (status?.pgbackrest_ready ? 'Készen áll' : 'Inicializálás')}</strong><small>v{status?.agent_version || '—'} · {status?.pgbackrest_stanza || '—'}</small></div>
        <div className="metric"><span>Offsite backup</span><strong>{status?.offsite?.enabled ? (status?.offsite?.configured ? 'Aktív' : 'Hibás konfiguráció') : 'Kikapcsolva'}</strong><small>{status?.offsite?.last_success_at ? `Utolsó siker: ${formatDate(status.offsite.last_success_at)}` : 'Még nincs sikeres offsite mentés'}</small></div>
      </div>

      {status?.offsite?.last_error && <div className="warning-box">Offsite backup hiba: {status.offsite.last_error}</div>}
      {status?.pgbackrest_error && <div className="warning-box">A pgBackRest repository még nem áll készen. Az agent automatikusan újrapróbálja az inicializálást. Részlet: {status.pgbackrest_error}</div>}

      <div className="two-col backup-config-grid">
        <div className="panel">
          <h2>Automatikus napi mentés</h2>
          <p className="muted">A napi időpont helyi idő szerint értendő. A hónap utolsó napja MASTER, a többi nap inkrementális. Ha nincs érvényes MASTER vagy változott a deployment, a rendszer automatikusan MASTER-re emeli a mentést.</p>
          <p className="muted">A DB és az archív/runtime fájlok konzisztenciája miatt a mentés idejére a backend és a frontend rövid időre leáll, majd automatikusan újraindul. A PostgreSQL közben futva marad.</p>
          <form className="grid-form one" onSubmit={saveSchedule}>
            <label className="checkbox"><input type="checkbox" checked={Boolean(schedule.enabled)} onChange={(e) => setSchedule((p) => ({ ...p, enabled: e.target.checked }))} /> Automatikus napi mentés engedélyezése</label>
            <Field label="Napi mentés időpontja"><input type="time" value={schedule.daily_time || '23:30'} onChange={(e) => setSchedule((p) => ({ ...p, daily_time: e.target.value }))} required /></Field>
            <Field label="Időzóna"><input value={schedule.timezone || 'Europe/Budapest'} onChange={(e) => setSchedule((p) => ({ ...p, timezone: e.target.value }))} required /></Field>
            <div className="form-actions"><button disabled={saving || busy || status?.restore_recovery_required}>{saving ? 'Mentés...' : 'Ütemezés mentése'}</button></div>
          </form>
          <p className="muted backup-last-run">Legutóbbi automatikus futási nap: {schedule.last_run_date || 'még nem futott'}</p>
          <p className="muted">A helyi pgBackRest repository retention-je továbbra is manuális; az offsite Restic repository külön napi/heti/havi retention szabályokat használ.</p>
        </div>

        <div className="panel">
          <h2>Visszaállítás mentési pontra</h2>
          {!canRestore && <p>A visszaállításhoz <code>admin.backup.restore</code> jogosultság szükséges.</p>}
          {canRestore && (
            <form className="grid-form one" onSubmit={restoreSelected}>
              <p className="muted">A webes restore csak az aktuálisan telepített deploymenthez tartozó mentést fogad el. Más alkalmazásverzió visszaállításához a host restore scriptet kell használni.</p>
              <p className="muted">A rendszer először kötelező pre-restore MASTER-t készít, ellenőrzi a teljes mentési láncot, visszaállítja a PostgreSQL-t és az <code>app_runtime</code> állapotot, majd új post-restore MASTER-rel új inkrementális láncot nyit.</p>
              <Field label="Visszaállítási pont">
                <select value={restoreBackupId} onChange={(e) => setRestoreBackupId(e.target.value)} required>
                  <option value="">Válassz mentési pontot...</option>
                  {compatibleBackups.map((row) => <option key={row.id} value={row.id}>{row.id} · {formatDate(row.finished_at)} · {jobKind(row)}</option>)}
                </select>
              </Field>
              <Field label="Megerősítés">
                <input value={restoreConfirmation} onChange={(e) => setRestoreConfirmation(e.target.value)} placeholder="VISSZAALLIT" autoComplete="off" />
              </Field>
              <div className="warning-box">A művelet felülírja a jelenlegi adatbázis- és runtime-állapotot. A visszaállítás alatt a webalkalmazás átmenetileg nem lesz elérhető.</div>
              <div className="form-actions">
                <button className="danger" disabled={restoring || busy || status?.restore_recovery_required || restoreConfirmation !== 'VISSZAALLIT'}>
                  {restoring ? 'Indítás...' : 'Visszaállítás indítása'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>

      <div className="panel">
        <h2>Mentési pontok</h2>
        {runningJob && <p className="backup-running">Aktív mentési feladat: <strong>{runningJob.id}</strong> · {statusLabel(runningJob.status)}</p>}
        <div className="table-wrap backup-table-wrap">
          <table className="backup-table">
            <thead><tr><th>Azonosító</th><th>Időpont</th><th>Típus</th><th>Indítás</th><th>Alap MASTER</th><th>DB backup</th><th>Offsite</th><th>Méret</th><th>Állapot</th><th>Művelet</th></tr></thead>
            <tbody>
              {jobs.length === 0 && <tr><td colSpan="10">Még nincs mentési pont.</td></tr>}
              {jobs.map((row) => (
                <tr key={row.id}>
                  <td><strong>{row.id}</strong>{row.message && <small>{row.message}</small>}{row.error && <small className="backup-error-text">{row.error}</small>}</td>
                  <td>{formatDate(row.finished_at || row.created_at)}</td>
                  <td>{jobKind(row)}</td>
                  <td>{triggerLabel(row.trigger)}</td>
                  <td>{row.base_master_id || '—'}</td>
                  <td>{row.pgbackrest_label || '—'}</td>
                  <td>{row.offsite_status ? statusLabel(row.offsite_status) : (status?.offsite?.enabled ? 'Várakozik' : '—')}</td>
                  <td>{row.size_bytes ? formatBytes(row.size_bytes) : '—'}</td>
                  <td>{statusLabel(row.status)}</td>
                  <td className="actions">
                    <button type="button" className="secondary" disabled={row.status !== 'success' || busy} onClick={() => validate(row)}>Ellenőrzés</button>
                    {canRestore && <button
                      type="button"
                      className="danger"
                      disabled={row.status !== 'success' || busy || status?.restore_recovery_required || !status?.deployment_fingerprint || row.deployment_fingerprint !== status.deployment_fingerprint}
                      title={row.deployment_fingerprint !== status?.deployment_fingerprint ? 'Más deploymenthez tartozó mentés csak host restore-ral állítható vissza.' : ''}
                      onClick={() => setRestoreBackupId(row.id)}
                    >Kiválasztás restore-hoz</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {canRestore && (
        <div className="panel">
          <h2>Visszaállítási előzmények</h2>
          {runningRestore && <p className="backup-running">Aktív restore: <strong>{runningRestore.id}</strong> · {statusLabel(runningRestore.status)}</p>}
          <div className="table-wrap backup-table-wrap">
            <table className="backup-table">
              <thead><tr><th>Restore azonosító</th><th>Cél mentés</th><th>Indítás</th><th>Pre-restore MASTER</th><th>Post-restore MASTER</th><th>Rollback MASTER</th><th>Rollback</th><th>Állapot</th></tr></thead>
              <tbody>
                {restores.length === 0 && <tr><td colSpan="8">Még nem történt webes visszaállítás.</td></tr>}
                {restores.map((row) => (
                  <tr key={row.id}>
                    <td><strong>{row.id}</strong>{row.message && <small>{row.message}</small>}{row.error && <small className="backup-error-text">{row.error}</small>}{row.rollback_error && <small className="backup-error-text">Rollback: {row.rollback_error}</small>}</td>
                    <td>{row.backup_id}</td>
                    <td>{formatDate(row.started_at || row.created_at)}</td>
                    <td>{row.pre_restore_backup_id || '—'}</td>
                    <td>{row.post_restore_backup_id || '—'}</td>
                    <td>{row.rollback_restore_backup_id || '—'}</td>
                    <td>{row.rollback_status || '—'}</td>
                    <td>{statusLabel(row.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}
