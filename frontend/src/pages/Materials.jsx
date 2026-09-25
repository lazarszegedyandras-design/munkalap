import React, { useEffect, useState } from 'react'
import { api } from '../api.js'
import DataTable from '../components/DataTable.jsx'
import { Field } from '../components/FormField.jsx'

const empty = { sku: '', name: '', unit: 'db', unit_price: '', stock: '', note: '' }

export default function Materials() {
  const [rows, setRows] = useState([])
  const [form, setForm] = useState(empty)
  const [editing, setEditing] = useState(null)
  const [q, setQ] = useState('')
  const [error, setError] = useState('')
  useEffect(() => { load() }, [q])
  async function load() { try { setRows(await api(`/materials?${new URLSearchParams(q ? { q } : {})}`)) } catch (err) { setError(err.message) } }
  function setField(k, v) { setForm((p) => ({ ...p, [k]: v })) }
  function normalize() { return { ...form, unit_price: form.unit_price === '' ? null : Number(form.unit_price), stock: form.stock === '' ? null : Number(form.stock) } }
  async function submit(e) {
    e.preventDefault(); setError('')
    try {
      if (editing) await api(`/materials/${editing}`, { method: 'PUT', body: normalize() })
      else await api('/materials', { method: 'POST', body: normalize() })
      setForm(empty); setEditing(null); load()
    } catch (err) { setError(err.message) }
  }
  function edit(row) { setEditing(row.id); setForm({ sku: row.sku, name: row.name, unit: row.unit, unit_price: row.unit_price ?? '', stock: row.stock ?? '', note: row.note ?? '' }) }
  async function remove(row) { if (confirm('Biztosan törlöd az anyagot?')) { await api(`/materials/${row.id}`, { method: 'DELETE' }); load() } }
  return (
    <section>
      <div className="page-head"><h1>Anyagok</h1></div>
      {error && <div className="error">{error}</div>}
      <div className="panel">
        <h2>{editing ? 'Anyag szerkesztése' : 'Új anyag'}</h2>
        <form className="grid-form" onSubmit={submit}>
          <Field label="Cikkszám"><input value={form.sku} onChange={(e) => setField('sku', e.target.value)} required /></Field>
          <Field label="Név"><input value={form.name} onChange={(e) => setField('name', e.target.value)} required /></Field>
          <Field label="Mennyiségi egység"><input value={form.unit} onChange={(e) => setField('unit', e.target.value)} required /></Field>
          <Field label="Egységár"><input type="number" step="0.01" value={form.unit_price} onChange={(e) => setField('unit_price', e.target.value)} /></Field>
          <Field label="Készlet"><input type="number" step="0.01" value={form.stock} onChange={(e) => setField('stock', e.target.value)} /></Field>
          <Field label="Megjegyzés"><textarea value={form.note} onChange={(e) => setField('note', e.target.value)} /></Field>
          <div className="form-actions"><button>{editing ? 'Mentés' : 'Létrehozás'}</button>{editing && <button type="button" className="secondary" onClick={() => { setEditing(null); setForm(empty) }}>Mégse</button>}</div>
        </form>
      </div>
      <div className="filters"><input placeholder="Keresés cikkszám vagy név szerint" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <DataTable rows={rows} columns={[{ key: 'sku', label: 'Cikkszám' }, { key: 'name', label: 'Név' }, { key: 'unit', label: 'ME' }, { key: 'unit_price', label: 'Egységár' }, { key: 'stock', label: 'Készlet' }]} actions={(row) => <><button onClick={() => edit(row)}>Szerkesztés</button><button className="danger" onClick={() => remove(row)}>Törlés</button></>} />
    </section>
  )
}
