import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MODULES } from '../utils/permissions.js'
import { api } from '../api.js'

const cards = [
  {
    code: 'service',
    title: 'Szerviz',
    description: 'Munkalapok, eszközök, ügyfelek, anyagok és munkalap-archívum.',
  },
  {
    code: 'hr',
    title: 'HR',
    description: 'Saját szabadságkeret, szabadságigénylés, vezetői jóváhagyás és jogosultsághoz kötött összesítés.',
  },
  {
    code: 'crm',
    title: 'CRM',
    description: 'Közös ügyféltörzs, 360° ügyfélkép, értékesítési lehetőségek és CRM aktivitások.',
  },
  {
    code: 'procurement',
    title: 'Beszerzés',
    description: 'Beszerzési igények létrehozása, nyomon követése és jogosultsághoz kötött jóváhagyása.',
  },
  {
    code: 'admin',
    title: 'Admin',
    description: 'Jogosultság szerint elérhető rendszeradminisztráció és biztonsági mentések.',
  },
]

export default function ModuleSelector({ user, appInfo, onLogout }) {
  const navigate = useNavigate()
  const [notifications, setNotifications] = useState([])
  useEffect(() => { api('/notifications?unread_only=true&limit=100').then(setNotifications).catch(() => {}) }, [])
  const unreadByModule = notifications.reduce((acc, row) => { acc[row.module] = (acc[row.module] || 0) + 1; return acc }, {})
  const available = cards.filter((card) => user?.modules?.includes(card.code))

  return (
    <main className="module-selector-page">
      <section className="module-selector-shell">
        <div className="module-selector-head">
          <div>
            <p className="eyebrow">Munkalap rendszer {appInfo?.version ? `v${appInfo.version}` : ''}</p>
            <h1>Modulválasztó</h1>
            <p className="muted">Bejelentkezve: {user?.full_name} · {user?.role?.name}</p>
          </div>
          <div className="inline-actions">
            <button className="secondary" onClick={() => navigate('/notifications')}>Értesítések{notifications.length ? ` (${notifications.length})` : ''}</button>
            <button className="secondary" onClick={() => navigate('/change-password')}>Jelszó módosítása</button>
            <button onClick={onLogout}>Kilépés</button>
          </div>
        </div>

        {available.length ? (
          <div className="module-card-grid">
            {available.map((card) => (
              <button
                key={card.code}
                type="button"
                className="module-card"
                onClick={() => navigate(MODULES[card.code].route)}
              >
                <span className="module-card-title">{card.title}{unreadByModule[card.code] ? <span className="module-card-unread">{unreadByModule[card.code]}</span> : null}</span>
                <span className="module-card-description">{card.description}</span>
                <span className="module-card-action">Modul megnyitása →</span>
              </button>
            ))}
          </div>
        ) : (
          <div className="panel">
            <h2>Nincs engedélyezett modul</h2>
            <p>Ehhez a felhasználóhoz jelenleg nincs modul-hozzáférés rendelve. Kérj jogosultságot egy rendszergazdától.</p>
          </div>
        )}
      </section>
    </main>
  )
}
