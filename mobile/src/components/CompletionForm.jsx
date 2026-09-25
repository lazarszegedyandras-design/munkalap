import { useEffect, useState } from 'react'

export default function CompletionForm({ order, api, onCompleted, onCancel }) {
  const [workDone, setWorkDone] = useState(order.work_done || '')
  const [finalStatus, setFinalStatus] = useState(order.final_status || '')
  const [laborHours, setLaborHours] = useState(order.labor_hours ?? '')
  const [customerNote, setCustomerNote] = useState(order.customer_note || '')
  const [internalNote, setInternalNote] = useState(order.internal_note || '')
  const [materials, setMaterials] = useState((order.materials || []).map(m => ({ material_id: m.material_id, name: m.name, quantity: m.quantity, unit_price: m.unit_price, note: m.note || '' })))
  const [query, setQuery] = useState('')
  const [options, setOptions] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { const t=setTimeout(async()=>{ if(query.trim().length<2){setOptions([]);return} try{setOptions(await api(`/materials?q=${encodeURIComponent(query.trim())}`))}catch{} },300); return()=>clearTimeout(t)},[query])
  function addMaterial(m) { if (!materials.some(x=>x.material_id===m.id)) setMaterials([...materials,{material_id:m.id,name:m.name,quantity:1,unit_price:m.unit_price,note:''}]); setQuery('');setOptions([]) }
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError('')
    try {
      const payload={version:order.version,work_done:workDone.trim(),final_status:finalStatus.trim()||null,labor_hours:laborHours===''?null:Number(laborHours),customer_note:customerNote.trim()||null,internal_note:internalNote.trim()||null,materials:materials.map(m=>({material_id:m.material_id,quantity:Number(m.quantity),unit_price:m.unit_price==null?null:Number(m.unit_price),note:m.note||null}))}
      const snapshot=await api(`/work-orders/${order.id}/complete`,{method:'POST',body:payload}); onCompleted(snapshot)
    } catch(e){setError(e.message)} finally{setBusy(false)}
  }
  return <main><header className="app-header"><button className="icon-btn" onClick={onCancel}>‹ Vissza</button><strong>Munka befejezése</strong><span/></header><form className="page stack" onSubmit={submit}>
    <label>Elvégzett munka *<textarea rows="6" required value={workDone} onChange={e=>setWorkDone(e.target.value)} /></label>
    <label>Végállapot<input value={finalStatus} onChange={e=>setFinalStatus(e.target.value)} placeholder="pl. üzemképes" /></label>
    <label>Munkaóra<input type="number" min="0" max="24" step="0.25" value={laborHours} onChange={e=>setLaborHours(e.target.value)} /></label>
    <label>Ügyfélnek látható megjegyzés<textarea rows="3" value={customerNote} onChange={e=>setCustomerNote(e.target.value)} /></label>
    <label>Belső megjegyzés<textarea rows="3" value={internalNote} onChange={e=>setInternalNote(e.target.value)} /></label>
    <section className="panel"><h2>Felhasznált anyagok</h2><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Cikkszám vagy megnevezés keresése" />{options.length>0&&<div className="search-results">{options.map(m=><button type="button" key={m.id} onClick={()=>addMaterial(m)}>{m.sku} – {m.name}</button>)}</div>}{materials.map((m,i)=><div className="material-row" key={m.material_id}><span>{m.name}</span><input aria-label="Mennyiség" type="number" min="0.01" step="0.01" value={m.quantity} onChange={e=>setMaterials(materials.map((x,j)=>j===i?{...x,quantity:e.target.value}:x))}/><button type="button" className="text-danger" onClick={()=>setMaterials(materials.filter((_,j)=>j!==i))}>×</button></div>)}</section>
    {error&&<div className="error-box">{error}</div>}<button className="btn primary" disabled={busy}>{busy?'Mentés…':'Aláírásra előkészítés'}</button>
  </form></main>
}
