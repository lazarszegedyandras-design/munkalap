import React, { useEffect, useState } from 'react'
import { api, exportUrl } from '../api.js'
import { Field } from '../components/FormField.jsx'
import { useSecurityStepUp } from '../components/SecurityStepUpModal.jsx'
import { hasPermission } from '../utils/permissions.js'

const emptyTechnician = { email: '', full_name: '', password: '', is_active: true }

export default function Settings({ user, appInfo }) {
  const { runSensitive, stepUpModal } = useSecurityStepUp()
  const isAdmin = user?.role?.name === 'Admin'
  const canRestore = hasPermission(user, 'admin.backup.restore')
  const [globalImportFile, setGlobalImportFile] = useState(null)
  const [globalImportResult, setGlobalImportResult] = useState(null)
  const [globalImportLoading, setGlobalImportLoading] = useState(false)
  const [companyProfiles, setCompanyProfiles] = useState([])
  const [editingCompanyCode, setEditingCompanyCode] = useState(null)
  const [companyForm, setCompanyForm] = useState(null)
  const [technicians, setTechnicians] = useState([])
  const [technicianForm, setTechnicianForm] = useState(emptyTechnician)
  const [editingTechnician, setEditingTechnician] = useState(null)
  const [backupFile, setBackupFile] = useState(null)
  const [restoreConfirmation, setRestoreConfirmation] = useState('')
  const [restoreLoading, setRestoreLoading] = useState(false)
  const [restoreResult, setRestoreResult] = useState(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    loadCompanyProfiles()
    if (isAdmin) loadTechnicians()
  }, [isAdmin])

  async function loadCompanyProfiles() {
    try {
      setCompanyProfiles(await api('/settings/companies'))
    } catch (err) {
      setError(err.message)
    }
  }

  async function loadTechnicians() {
    try {
      setTechnicians(await api('/settings/technicians'))
    } catch (err) {
      setError(err.message)
    }
  }

  function editCompany(company) {
    setEditingCompanyCode(company.code)
    setCompanyForm({ ...company, aliases: (company.aliases || []).join(', ') })
  }

  function setCompanyField(key, value) {
    setCompanyForm((current) => ({ ...current, [key]: value }))
  }

  function cancelCompanyEdit() {
    setEditingCompanyCode(null)
    setCompanyForm(null)
  }

  async function saveCompany(event) {
    event.preventDefault()
    if (!editingCompanyCode || !companyForm) return
    setError('')
    setSuccess('')
    try {
      const payload = {
        ...companyForm,
        aliases: companyForm.aliases.split(',').map((value) => value.trim()).filter(Boolean),
      }
      delete payload.code
      delete payload.source
      delete payload.source_urls
      delete payload.display_name
      delete payload.address_for_worksheet
      delete payload.phone_for_worksheet
      delete payload.email_for_worksheet
      await api(`/settings/companies/${editingCompanyCode}`, { method: 'PUT', body: payload })
      setSuccess('A szállítói adatok mentése sikerült. Az új adatok azonnal megjelennek a nyomtatási képen és a kompatibilitási Excel-exportban.')
      cancelCompanyEdit()
      await loadCompanyProfiles()
    } catch (err) {
      setError(err.message)
    }
  }

  async function runGlobalImport(previewOnly) {
    if (!globalImportFile) {
      setError('Válassz ki egy globális import Excel fájlt.')
      return
    }
    setError('')
    setSuccess('')
    setGlobalImportLoading(true)
    try {
      const formData = new FormData()
      formData.append('import_file', globalImportFile)
      const result = await api(`/imports/global/${previewOnly ? 'preview' : 'run'}`, { method: 'POST', body: formData })
      setGlobalImportResult(result)
      if (!previewOnly) {
        setSuccess(
          `Globális import kész: ${result.assets_created} új és ${result.assets_updated} frissített eszköz, ` +
          `${result.meter_readings_imported} számlálóállás, ${result.skipped_count} kihagyott sor.`
        )
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setGlobalImportLoading(false)
    }
  }

  function setTechnicianField(key, value) {
    setTechnicianForm((current) => ({ ...current, [key]: value }))
  }

  function editTechnician(technician) {
    setEditingTechnician(technician.id)
    setTechnicianForm({
      email: technician.email,
      full_name: technician.full_name,
      password: '',
      is_active: technician.is_active,
    })
  }

  function resetTechnicianForm() {
    setEditingTechnician(null)
    setTechnicianForm(emptyTechnician)
  }

  async function saveTechnician(event) {
    event.preventDefault()
    setError('')
    setSuccess('')
    try {
      const payload = { ...technicianForm }
      if (editingTechnician && !payload.password) delete payload.password
      if (editingTechnician) {
        await api(`/settings/technicians/${editingTechnician}`, { method: 'PATCH', body: payload })
        setSuccess('A technikus adatai frissültek.')
      } else {
        await api('/settings/technicians', { method: 'POST', body: payload })
        setSuccess('A technikus létrejött.')
      }
      resetTechnicianForm()
      await loadTechnicians()
    } catch (err) {
      setError(err.message)
    }
  }

  async function deleteTechnician(technician) {
    if (!window.confirm(`Biztosan törlöd ezt a technikust: ${technician.full_name}? A hozzá rendelt nyitott munkalapok felelőse üres lesz.`)) return
    setError('')
    setSuccess('')
    try {
      await api(`/settings/technicians/${technician.id}`, { method: 'DELETE' })
      if (editingTechnician === technician.id) resetTechnicianForm()
      setSuccess('A technikus törölve lett.')
      await loadTechnicians()
    } catch (err) {
      setError(err.message)
    }
  }

  async function download(path, filename) {
    try {
      const response = await fetch(exportUrl(path), { credentials: 'include' })
      if (!response.ok) {
        let message = response.statusText
        try { message = (await response.json()).detail || message } catch { /* nem JSON válasz */ }
        throw new Error(message)
      }
      const blob = await response.blob()
      const contentDisposition = response.headers.get('content-disposition') || ''
      const filenameMatch = contentDisposition.match(/filename="?([^";]+)"?/i)
      const resolvedFilename = filenameMatch?.[1] || filename
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = resolvedFilename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    }
  }

  async function restoreBackup(event) {
    event.preventDefault()
    if (!backupFile) {
      setError('Válassz ki egy korábban exportált ZIP mentést.')
      return
    }
    setError('')
    setSuccess('')
    setRestoreResult(null)
    setRestoreLoading(true)
    try {
      const formData = new FormData()
      formData.append('backup_file', backupFile)
      formData.append('confirmation', restoreConfirmation)
      const result = await runSensitive(() => api('/settings/restore', { method: 'POST', body: formData }))
      setRestoreResult(result)
      setSuccess(result.message)
      setBackupFile(null)
      setRestoreConfirmation('')
      const fileInput = document.getElementById('full-backup-file')
      if (fileInput) fileInput.value = ''
    } catch (err) {
      setError(err.message)
    } finally {
      setRestoreLoading(false)
    }
  }

  return (
    <section>
      {stepUpModal}
      <div className="page-head"><h1>Beállítások</h1></div>
      {error && <div className="error">{error}</div>}
      {success && <div className="success">{success}</div>}

      {isAdmin && (
        <div className="panel">
          <h2>Technikusok</h2>
          <p className="muted">Az itt létrehozott felhasználók automatikusan „Technikus / szerelő” jogosultságot kapnak, és kiválaszthatók lesznek a munkalapokon.</p>
          <form className="grid-form" onSubmit={saveTechnician}>
            <Field label="Név"><input value={technicianForm.full_name} onChange={(e) => setTechnicianField('full_name', e.target.value)} required /></Field>
            <Field label="Email"><input type="email" value={technicianForm.email} onChange={(e) => setTechnicianField('email', e.target.value)} required /></Field>
            <Field label={editingTechnician ? 'Új jelszó' : 'Jelszó'}><input type="password" value={technicianForm.password} onChange={(e) => setTechnicianField('password', e.target.value)} required={!editingTechnician} minLength={8} autoComplete="new-password" placeholder={editingTechnician ? 'Üresen hagyva nem változik' : 'Min. 8 karakter, nagybetű, speciális jel'} /></Field>
            <label className="checkbox"><input type="checkbox" checked={technicianForm.is_active} onChange={(e) => setTechnicianField('is_active', e.target.checked)} /> Aktív</label>
            <div className="form-actions">
              <button>{editingTechnician ? 'Technikus mentése' : 'Technikus hozzáadása'}</button>
              {editingTechnician && <button type="button" className="secondary" onClick={resetTechnicianForm}>Mégse</button>}
            </div>
          </form>
          <div className="mini-table-wrap settings-table-spacing">
            <table className="mini-table">
              <thead><tr><th>Név</th><th>Email</th><th>Állapot</th><th>Műveletek</th></tr></thead>
              <tbody>
                {technicians.map((technician) => (
                  <tr key={technician.id}>
                    <td>{technician.full_name}</td>
                    <td>{technician.email}</td>
                    <td>{technician.is_active ? 'Aktív' : 'Inaktív'}</td>
                    <td className="actions">
                      <button type="button" onClick={() => editTechnician(technician)}>Szerkesztés</button>
                      <button type="button" className="danger" onClick={() => deleteTechnician(technician)}>Törlés</button>
                    </td>
                  </tr>
                ))}
                {!technicians.length && <tr><td colSpan="4">Még nincs technikus rögzítve.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(isAdmin || canRestore) && (
        <div className="panel">
          <h2>Teljes adatbázis- és beállításmentés</h2>
          <p>A mentés egy ZIP fájlba teszi a teljes alkalmazás-adatbázist, a felhasználókat és jogosultságokat, a munkalapokat, eszközöket, ügyfeleket, anyagokat, naplókat, cégprofilokat, valamint a munkalap Excel-sablont és az alkalmazásbeállításokat.</p>
          <div className="warning-box"><strong>Bizalmas adat:</strong> a mentés felhasználói és alkalmazásbiztonsági adatokat is tartalmaz. Tárold hozzáférésvédett helyen.</div>
          {isAdmin && <div className="form-actions">
            <button type="button" onClick={() => download('/settings/backup', 'munkalap-teljes-mentes.zip')}>Teljes mentés letöltése</button>
          </div>}
          <hr className="panel-separator" />
          <h3>Teljes visszaállítás</h3>
          <p className="muted">A művelet a jelenlegi adatbázis teljes tartalmát lecseréli a mentésben lévő adatokra. A PostgreSQL elérését és a Docker portokat a célgép meglévő <code>.env</code> fájlja tartja meg.</p>
          <form className="grid-form one" onSubmit={restoreBackup}>
            <Field label="Mentési ZIP fájl"><input id="full-backup-file" type="file" accept=".zip,application/zip" onChange={(e) => setBackupFile(e.target.files?.[0] || null)} required /></Field>
            <Field label='Megerősítés: írd be, hogy „VISSZAÁLLÍTÁS”'><input value={restoreConfirmation} onChange={(e) => setRestoreConfirmation(e.target.value)} required /></Field>
            <div className="form-actions"><button className="danger" disabled={restoreLoading}>{restoreLoading ? 'Visszaállítás folyamatban...' : 'Teljes visszaállítás indítása'}</button></div>
          </form>
          {restoreResult && (
            <div className="success restore-result">
              <strong>Visszaállítás befejezve.</strong>
              <p>Mentés időpontja: {restoreResult.backup_created_at || '-'}</p>
              <p>Mentés alkalmazásverziója: {restoreResult.backup_application_version ? `v${restoreResult.backup_application_version}` : 'régi mentés / nincs adat'}</p>
              <p>A beállítások teljes alkalmazásához futtasd:</p>
              <code>docker compose restart backend</code>
              <p>Ezután jelentkezz be a mentésben szereplő felhasználói adatokkal.</p>
            </div>
          )}
        </div>
      )}

      {isAdmin && (
        <div className="panel">
          <h2>Globális Excel import/export</h2>
          <p className="muted">Egyetlen munkafüzetből kezelhető az ügyfél-, helyszín-, eszköz-, kapcsolattartó-, karbantartási ciklus-, utolsó karbantartási és számlálóadat-import.</p>
          <div className="warning-box"><strong>Ajánlott folyamat:</strong> töltsd le a mintafájlt, töltsd ki a megfelelő munkalapokat, majd először futtasd az ellenőrzést. Az üres cellák nem törlik a meglévő adatokat.</div>
          <div className="form-actions">
            <button type="button" className="secondary" onClick={() => download('/imports/global/template', 'globalis_import_minta.xlsx')}>Mintafájl letöltése</button>
            <button type="button" onClick={() => download('/imports/global/export', 'globalis_adat_export.xlsx')}>Jelenlegi adatok exportálása</button>
          </div>
          <p className="muted">Az export ugyanazokat a munkalapokat és oszlopokat használja, mint a globális import, ezért közvetlenül visszaimportálható. Az eszközök, kapcsolattartók, karbantartási adatok és számlálóelőzmények kerülnek bele.</p>
          <div className="grid-form one">
            <Field label="Globális import Excel fájl">
              <input
                id="global-import-file"
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(event) => {
                  setGlobalImportFile(event.target.files?.[0] || null)
                  setGlobalImportResult(null)
                }}
              />
            </Field>
          </div>
          <div className="form-actions">
            <button type="button" className="secondary" disabled={globalImportLoading || !globalImportFile} onClick={() => runGlobalImport(true)}>
              {globalImportLoading ? 'Feldolgozás...' : 'Import ellenőrzése'}
            </button>
            <button type="button" disabled={globalImportLoading || !globalImportFile} onClick={() => runGlobalImport(false)}>
              {globalImportLoading ? 'Feldolgozás...' : 'Globális import indítása'}
            </button>
          </div>
          {globalImportResult && (
            <div className="import-result-block">
              <h3>{globalImportResult.mode === 'preview' ? 'Ellenőrzési eredmény' : 'Import eredménye'}</h3>
              <ul className="inline-list">
                <li><strong>Eszközök lap:</strong> {globalImportResult.asset_rows} sor</li>
                <li><strong>Kapcsolattartók lap:</strong> {globalImportResult.contact_rows} sor</li>
                <li><strong>Számlálók lap:</strong> {globalImportResult.meter_rows} sor</li>
              </ul>
              <div className="metric-grid compact-metrics">
                <div className="metric"><span>Új ügyfél</span><strong>{globalImportResult.customers_created}</strong></div>
                <div className="metric"><span>Frissített ügyfél</span><strong>{globalImportResult.customers_updated}</strong></div>
                <div className="metric"><span>Új helyszín</span><strong>{globalImportResult.locations_created}</strong></div>
                <div className="metric"><span>Új / frissített kapcsolattartó</span><strong>{globalImportResult.contacts_created + globalImportResult.contacts_updated}</strong></div>
                <div className="metric"><span>Új eszköz</span><strong>{globalImportResult.assets_created}</strong></div>
                <div className="metric"><span>Frissített eszköz</span><strong>{globalImportResult.assets_updated}</strong></div>
                <div className="metric"><span>Karbantartási dátum</span><strong>{globalImportResult.maintenance_dates_updated}</strong></div>
                <div className="metric"><span>Karbantartási ciklus</span><strong>{globalImportResult.maintenance_cycles_updated}</strong></div>
                <div className="metric"><span>{globalImportResult.mode === 'preview' ? 'Importálható számláló' : 'Importált számláló'}</span><strong>{globalImportResult.mode === 'preview' ? globalImportResult.meter_readings_would_import : globalImportResult.meter_readings_imported}</strong></div>
                <div className="metric"><span>Változatlan számláló</span><strong>{globalImportResult.meter_readings_unchanged}</strong></div>
                <div className="metric"><span>Ütközés</span><strong>{globalImportResult.maintenance_conflicts + globalImportResult.meter_conflicts}</strong></div>
                <div className="metric"><span>Kihagyott sor</span><strong>{globalImportResult.skipped_count}</strong></div>
              </div>
              {globalImportResult.issues?.length > 0 && (
                <>
                  <h3>Figyelmeztetések és hibák</h3>
                  <div className="mini-table-wrap">
                    <table className="mini-table">
                      <thead><tr><th>Munkalap</th><th>Excel sor</th><th>Adattípus</th><th>Azonosító</th><th>Ok</th></tr></thead>
                      <tbody>
                        {globalImportResult.issues.map((issue, index) => (
                          <tr key={`${issue.sheet}-${issue.excel_row || 'x'}-${index}`}>
                            <td>{issue.sheet}</td>
                            <td>{issue.excel_row || '-'}</td>
                            <td>{issue.entity}</td>
                            <td>{issue.identifier || '-'}</td>
                            <td>{issue.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {globalImportResult.issues_truncated && <p className="muted">A lista csak az első 200 problémát mutatja.</p>}
                </>
              )}
            </div>
          )}
          <p className="muted">A korábbi külön importformátumok backend végpontjai kompatibilitási okból megmaradnak, de az admin felületen kizárólag ez az egységes import használható.</p>
        </div>
      )}

      <div className="panel">
        <h2>Nyomtatási szállítói adatok</h2>
        <p className="muted">A nyomtatott munkalap fejlécének szállítói adatai innen származnak. A rendszer a munkalap ügyfelén vagy kapcsolt eszközén lévő cégkód alapján választ profilt. A külön munkalapi telefon és email elsőbbséget élvez az általános kapcsolati adatokkal szemben; így a nyomtatásban központi helpdesk/szolgáltatási elérhetőség használható anélkül, hogy a cég általános adatait át kellene írni.</p>
        {isAdmin && companyForm && (
          <form className="company-edit-form" onSubmit={saveCompany}>
            <h3>{companyForm.code} – cégadatok szerkesztése</h3>
            <div className="grid-form">
              <Field label="Rövid cégnév"><input value={companyForm.short_name || ''} onChange={(e) => setCompanyField('short_name', e.target.value)} required /></Field>
              <Field label="Teljes cégnév"><input value={companyForm.legal_name || ''} onChange={(e) => setCompanyField('legal_name', e.target.value)} /></Field>
              <Field label="Cégkód-aliasok"><input value={companyForm.aliases || ''} onChange={(e) => setCompanyField('aliases', e.target.value)} placeholder="DRH, DRh" /></Field>
              <Field label="Adószám"><input value={companyForm.tax_number || ''} onChange={(e) => setCompanyField('tax_number', e.target.value)} /></Field>
              <Field label="Cégjegyzékszám"><input value={companyForm.company_registration_number || ''} onChange={(e) => setCompanyField('company_registration_number', e.target.value)} /></Field>
              <Field label="Székhely"><input value={companyForm.registered_address || ''} onChange={(e) => setCompanyField('registered_address', e.target.value)} /></Field>
              <Field label="Kapcsolati cím"><input value={companyForm.contact_address || ''} onChange={(e) => setCompanyField('contact_address', e.target.value)} /></Field>
              <Field label="Telefon"><input value={companyForm.phone || ''} onChange={(e) => setCompanyField('phone', e.target.value)} /></Field>
              <Field label="Mobiltelefon"><input value={companyForm.mobile_phone || ''} onChange={(e) => setCompanyField('mobile_phone', e.target.value)} /></Field>
              <Field label="Email"><input type="email" value={companyForm.email || ''} onChange={(e) => setCompanyField('email', e.target.value)} /></Field>
              <Field label="Munkalapi szolgáltatási telefon"><input value={companyForm.worksheet_phone || ''} onChange={(e) => setCompanyField('worksheet_phone', e.target.value)} placeholder="pl. vezetékes / szolgáltatási mobil" /></Field>
              <Field label="Munkalapi helpdesk email"><input type="email" value={companyForm.worksheet_email || ''} onChange={(e) => setCompanyField('worksheet_email', e.target.value)} /></Field>
              <Field label="Weboldal"><input value={companyForm.website || ''} onChange={(e) => setCompanyField('website', e.target.value)} /></Field>
              <Field label="Kapcsolattartó"><input value={companyForm.contact_person || ''} onChange={(e) => setCompanyField('contact_person', e.target.value)} /></Field>
              <Field label="Tevékenység"><input value={companyForm.activity || ''} onChange={(e) => setCompanyField('activity', e.target.value)} /></Field>
              <Field label="Forrás / belső megjegyzés" className="company-source-note"><textarea value={companyForm.source_note || ''} onChange={(e) => setCompanyField('source_note', e.target.value)} /></Field>
            </div>
            <div className="form-actions"><button>Mentés</button><button type="button" className="secondary" onClick={cancelCompanyEdit}>Mégse</button></div>
          </form>
        )}
        {companyProfiles.length ? (
          <div className="mini-table-wrap">
            <table className="mini-table">
              <thead><tr><th>Kód</th><th>Cég</th><th>Adószám</th><th>Cégjegyzékszám</th><th>Székhely</th><th>Kapcsolat</th>{isAdmin && <th>Művelet</th>}</tr></thead>
              <tbody>
                {companyProfiles.map(company => (
                  <tr key={company.code}>
                    <td><strong>{company.code}</strong></td>
                    <td>{company.short_name}<br /><span className="muted">{company.legal_name}</span></td>
                    <td>{company.tax_number || '-'}</td>
                    <td>{company.company_registration_number || '-'}</td>
                    <td>{company.registered_address || '-'}</td>
                    <td>{company.phone || '-'}<br />{company.email || '-'}</td>
                    {isAdmin && <td><button type="button" onClick={() => editCompany(company)}>Szerkesztés</button></td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p>Cégadatok betöltése...</p>}
      </div>

      <div className="panel">
        <h2>Rendszerinformáció</h2>
        <div className="system-info-grid">
          <div><span>Alkalmazásverzió</span><strong>{appInfo?.version ? `v${appInfo.version}` : "v–"}</strong></div>
          <div><span>Mentési formátum</span><strong>{appInfo?.backup_format_version ?? "-"}</strong></div>
          <div><span>Verziózási séma</span><strong>Semantic Versioning</strong></div>
        </div>
        <p>Backend API dokumentáció: <a href="/docs" target="_blank" rel="noreferrer">Swagger / OpenAPI</a></p>
        <p>CSV exportok:</p>
        <div className="form-actions"><button onClick={() => download('/export/assets.csv', 'eszkozok.csv')}>Eszközlista CSV</button><button onClick={() => download('/export/work-orders.csv', 'munkalapok.csv')}>Munkalaplista CSV</button></div>
      </div>
      <div className="panel">
        <h2>Fejlesztői megjegyzés</h2>
        <p>A portok és az adatbázis-kapcsolat a projekt gyökerében található .env fájlban állíthatók. A migráció és seed a backend konténer indulásakor automatikusan lefut.</p>
      </div>
    </section>
  )
}
