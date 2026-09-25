import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import DataTable from '../components/DataTable.jsx'
import { Field } from '../components/FormField.jsx'
import { moduleLabel } from '../utils/permissions.js'
import { useSecurityStepUp } from '../components/SecurityStepUpModal.jsx'

const empty = { email: '', full_name: '', password: '', role_id: '', is_active: true, permission_codes: ['service.access'] }
const moduleOrder = ['service', 'hr', 'crm', 'procurement', 'admin']

export default function Users({ user }) {
  const { runSensitive, stepUpModal } = useSecurityStepUp()
  const [users, setUsers] = useState([])
  const [roles, setRoles] = useState([])
  const [permissions, setPermissions] = useState([])
  const [form, setForm] = useState(empty)
  const [editing, setEditing] = useState(null)
  const [error, setError] = useState('')
  const [deviceUser, setDeviceUser] = useState(null)
  const [devices, setDevices] = useState([])
  const [deviceBusy, setDeviceBusy] = useState(false)
  const isAdmin = user?.role?.name === 'Admin'
  const editingSelf = editing === user?.id
  const selectedRole = roles.find((role) => String(role.id) === String(form.role_id))
  const selectedIsAdmin = selectedRole?.name === 'Admin'

  const permissionsByModule = useMemo(() => {
    const groups = {}
    for (const permission of permissions) {
      if (!groups[permission.module]) groups[permission.module] = []
      groups[permission.module].push(permission)
    }
    return groups
  }, [permissions])

  useEffect(() => { load() }, [])

  async function load() {
    try {
      const [rs, ps] = await Promise.all([api('/users/roles'), api('/users/permissions')])
      setRoles(rs)
      setPermissions(ps)
      if (isAdmin) setUsers(await api('/users'))
    } catch (err) { setError(err.message) }
  }

  function setField(k, v) { setForm((p) => ({ ...p, [k]: v })) }

  function togglePermission(permission, checked) {
    setForm((current) => {
      const selected = new Set(current.permission_codes || [])
      const modulePermissions = permissionsByModule[permission.module] || []
      const moduleAccess = modulePermissions.find((item) => item.is_module_access)?.code
      if (checked) {
        selected.add(permission.code)
        if (!permission.is_module_access && moduleAccess) selected.add(moduleAccess)
        if (permission.code === 'hr.leave.request') selected.add('hr.leave.self')
        if (permission.code === 'admin.backup.restore') selected.add('admin.backup.manage')
      } else {
        selected.delete(permission.code)
        if (permission.code === 'hr.leave.self') selected.delete('hr.leave.request')
        if (permission.code === 'admin.backup.manage') selected.delete('admin.backup.restore')
        if (permission.is_module_access) {
          for (const item of modulePermissions) selected.delete(item.code)
        }
      }
      return { ...current, permission_codes: [...selected].sort() }
    })
  }

  async function submit(e) {
    e.preventDefault(); setError('')
    try {
      const payload = { ...form, role_id: Number(form.role_id) }
      if (editing) {
        if (!payload.password) delete payload.password
        await runSensitive(() => api(`/users/${editing}`, { method: 'PATCH', body: payload }))
      } else {
        await runSensitive(() => api('/users', { method: 'POST', body: payload }))
      }
      setEditing(null); setForm(empty); await load()
    } catch (err) { setError(err.message) }
  }

  function edit(row) {
    setEditing(row.id)
    setForm({
      email: row.email,
      full_name: row.full_name,
      password: '',
      role_id: row.role.id,
      is_active: row.is_active,
      permission_codes: [...(row.permissions || [])],
    })
  }

  async function remove(row) {
    if (confirm('Biztosan törlöd a felhasználót?')) {
      await api(`/users/${row.id}`, { method: 'DELETE' })
      await load()
    }
  }


  async function loadDevices(row = deviceUser) {
    if (!row) return
    setDeviceBusy(true); setError('')
    try {
      setDevices(await api(`/users/${row.id}/mobile-devices`))
    } catch (err) { setError(err.message) }
    finally { setDeviceBusy(false) }
  }

  async function openDevices(row) {
    setDeviceUser(row)
    setDevices([])
    await loadDevices(row)
  }

  async function revokeDevice(device) {
    if (!deviceUser || !confirm(`Biztosan visszavonod ezt a mobil eszközt: ${device.device_name || device.device_uuid}?`)) return
    setDeviceBusy(true); setError('')
    try {
      await api(`/users/${deviceUser.id}/mobile-devices/${device.id}`, { method: 'DELETE' })
      await loadDevices(deviceUser)
    } catch (err) { setError(err.message); setDeviceBusy(false) }
  }

  async function testPush(device) {
    if (!deviceUser) return
    setDeviceBusy(true); setError('')
    try {
      await api(`/users/${deviceUser.id}/mobile-devices/${device.id}/test-push`, { method: 'POST' })
      await loadDevices(deviceUser)
    } catch (err) { setError(err.message); setDeviceBusy(false) }
  }

  function fmtDate(value) {
    return value ? new Date(value).toLocaleString('hu-HU') : '—'
  }

  if (!isAdmin) return <section><h1>Felhasználók</h1><div className="panel">A felhasználókezelés admin jogosultsághoz kötött.</div></section>

  return (
    <section>
      {stepUpModal}
      <div className="page-head"><div><h1>Felhasználók</h1><p className="muted">Szerepkörök, modul-hozzáférések és funkciójogosultságok kezelése.</p></div></div>
      {error && <div className="error">{error}</div>}
      <div className="panel">
        <h2>{editing ? 'Felhasználó szerkesztése' : 'Új felhasználó'}</h2>
        <form className="grid-form" onSubmit={submit}>
          <Field label="Email"><input type="email" value={form.email} onChange={(e) => setField('email', e.target.value)} required /></Field>
          <Field label="Név"><input value={form.full_name} onChange={(e) => setField('full_name', e.target.value)} required /></Field>
          <Field label="Jelszó"><input type="password" value={form.password} onChange={(e) => setField('password', e.target.value)} required={!editing} disabled={editingSelf} minLength={8} autoComplete="new-password" placeholder={editingSelf ? 'Saját jelszó az oldalsávból módosítható' : (editing ? 'Üresen hagyva nem változik' : 'Min. 8 karakter, nagybetű, speciális jel')} /></Field>
          <Field label="Szerepkör"><select value={form.role_id} onChange={(e) => setField('role_id', e.target.value)} required><option value="">Válassz szerepkört</option>{roles.map(r => <option value={r.id} key={r.id}>{r.name}</option>)}</select></Field>
          <label className="checkbox"><input type="checkbox" checked={form.is_active} onChange={(e) => setField('is_active', e.target.checked)} /> Aktív</label>
          <div className="form-actions"><button>{editing ? 'Mentés' : 'Létrehozás'}</button>{editing && <button type="button" className="secondary" onClick={() => { setEditing(null); setForm(empty) }}>Mégse</button>}</div>

          <div className="permission-editor grid-form-full">
            <div className="permission-editor-head">
              <h3>Modulok és jogosultságok</h3>
              {selectedIsAdmin && <p className="muted">Az Admin szerepkör rendszerszintű hozzáférést kap minden modulhoz. Az alábbi tárolt jogok csak egy későbbi szerepkörváltásnál válnak meghatározóvá.</p>}
            </div>
            <div className="permission-groups">
              {moduleOrder.map((moduleCode) => (
                <fieldset className="permission-group" key={moduleCode}>
                  <legend>{moduleLabel(moduleCode)}</legend>
                  {(permissionsByModule[moduleCode] || []).map((permission) => (
                    <label className={`permission-option ${permission.is_module_access ? 'module-access' : ''}`} key={permission.code}>
                      <input
                        type="checkbox"
                        checked={(form.permission_codes || []).includes(permission.code)}
                        onChange={(e) => togglePermission(permission, e.target.checked)}
                      />
                      <span><strong>{permission.name}</strong><small>{permission.description}</small></span>
                    </label>
                  ))}
                </fieldset>
              ))}
            </div>
          </div>
        </form>
      </div>
      <DataTable
        rows={users}
        columns={[
          { key: 'email', label: 'Email' },
          { key: 'full_name', label: 'Név' },
          { key: 'role.name', label: 'Szerepkör' },
          { key: 'modules', label: 'Modulok', render: row => (row.modules || []).map(moduleLabel).join(', ') || 'nincs' },
          { key: 'is_active', label: 'Aktív', render: row => row.is_active ? 'igen' : 'nem' },
          { key: 'must_change_password', label: 'Jelszócsere', render: row => row.must_change_password ? 'kötelező' : 'nem' },
        ]}
        actions={(row) => <><button onClick={() => edit(row)}>Szerkesztés</button><button className="secondary" onClick={() => openDevices(row)}>Mobil eszközök</button><button className="danger" onClick={() => remove(row)}>Törlés</button></>}
      />
      {deviceUser && <div className="panel">
        <div className="page-head"><div><h2>Mobil eszközök – {deviceUser.full_name}</h2><p className="muted">Push állapot, utolsó kézbesítés és távoli eszköz-visszavonás. Az FCM token biztonsági okból nem jelenik meg.</p></div><div className="inline-actions"><button className="secondary" disabled={deviceBusy} onClick={() => loadDevices(deviceUser)}>Frissítés</button><button className="secondary" onClick={() => { setDeviceUser(null); setDevices([]) }}>Bezárás</button></div></div>
        {deviceBusy && <p className="muted">Frissítés…</p>}
        {!deviceBusy && !devices.length && <p className="muted">Ehhez a felhasználóhoz nincs regisztrált mobil eszköz.</p>}
        {!!devices.length && <div className="table-wrap"><table><thead><tr><th>Eszköz</th><th>App</th><th>Utolsó aktivitás</th><th>Push</th><th>Utolsó push</th><th>Műveletek</th></tr></thead><tbody>{devices.map((device) => <tr key={device.id}><td><strong>{device.device_name || device.device_uuid}</strong><br/><small>{device.platform} · ID {device.id}{device.revoked_at ? ` · visszavonva: ${fmtDate(device.revoked_at)}` : ''}</small></td><td>{device.app_version || '—'}</td><td>{fmtDate(device.last_seen_at)}</td><td>{device.push_enabled ? <>aktív<br/><small>{fmtDate(device.push_token_updated_at)}</small></> : 'nincs'}</td><td>{device.last_push ? <><strong>{device.last_push.status}</strong><br/><small>{fmtDate(device.last_push.sent_at || device.last_push.last_attempt_at || device.last_push.created_at)}{device.last_push.last_error ? ` · ${device.last_push.last_error}` : ''}</small></> : '—'}</td><td><div className="inline-actions"><button disabled={deviceBusy || !device.push_enabled || !!device.revoked_at} onClick={() => testPush(device)}>Teszt push</button><button className="danger" disabled={deviceBusy || !!device.revoked_at} onClick={() => revokeDevice(device)}>Visszavonás</button></div></td></tr>)}</tbody></table></div>}
      </div>}
    </section>
  )
}
