import { useState } from 'react'
import PhotoSection from './PhotoSection.jsx'
import { canEditWorkOrder, formatDateTime } from '../services/format.js'

export default function WorkOrderDetail({ order, api, onBack, onReload, onComplete, onSignedPdf }) {
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [meterValues,setMeterValues]=useState({})
  const editable=canEditWorkOrder(order.status)
  async function start(){setBusy(true);setError('');try{await api(`/work-orders/${order.id}/start`,{method:'POST',body:{version:order.version}});await onReload()}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function saveMeter(asset){const raw=meterValues[asset.id];if(raw==null||raw==='')return;setBusy(true);setError('');try{await api(`/work-orders/${order.id}/meter-readings`,{method:'POST',body:{asset_id:asset.id,value:Number(raw)}});setMeterValues({...meterValues,[asset.id]:''});await onReload()}catch(e){setError(e.message)}finally{setBusy(false)}}
  return <main><header className="app-header"><button className="icon-btn" onClick={onBack}>‹ Mai munkáim</button><strong>{order.number}</strong><span/></header><section className="page stack">
    <section className="hero"><div className="badges"><em>{order.status}</em><em>{order.priority||'normál'}</em></div><h1>{order.customer_name||'Ügyfél nélkül'}</h1><p>{order.location_name||order.location_address||order.customer_address||'–'}</p>{order.customer_phone&&<a className="btn secondary" href={`tel:${order.customer_phone}`}>☎ {order.customer_phone}</a>}</section>
    <section className="panel"><h2>Munkavégzés</h2><div className="kv"><span>Tervezett kezdés</span><strong>{formatDateTime(order.planned_start_at)}</strong><span>Munka típusa</span><strong>{order.work_type||'–'}</strong><span>Kapcsolattartó</span><strong>{order.customer_contact_person||'–'}</strong><span>Hiba / feladat</span><strong>{order.description||'–'}</strong>{order.internal_note&&<><span>Belső megjegyzés</span><strong>{order.internal_note}</strong></>}</div>{order.status!=='folyamatban'&&editable&&<button className="btn primary" disabled={busy} onClick={start}>Munka megkezdése</button>}</section>
    <section className="panel"><h2>Eszközök és számlálók</h2>{(order.assets||[]).map(a=><div className="asset-card" key={a.id}><strong>{a.display_name}</strong><small>Gyári szám: {a.serial_number||'–'}</small><small>Utolsó számláló: {a.latest_meter_value??'–'}</small>{editable&&<div className="inline"><input inputMode="numeric" type="number" min="0" placeholder="Új állás" value={meterValues[a.id]??''} onChange={e=>setMeterValues({...meterValues,[a.id]:e.target.value})}/><button className="btn secondary small" onClick={()=>saveMeter(a)} disabled={busy}>Rögzítés</button></div>}</div>)}</section>
    <PhotoSection order={order} api={api} onChanged={onReload}/>
    {(order.work_done||order.customer_note)&&<section className="panel"><h2>Elvégzett munka</h2><p className="prewrap">{order.work_done||'–'}</p>{order.customer_note&&<><h3>Ügyfél megjegyzés</h3><p className="prewrap">{order.customer_note}</p></>}</section>}
    {error&&<div className="error-box">{error}</div>}
    {editable&&<button className="btn primary big" onClick={onComplete}>Munka befejezése</button>}
    {order.status==='kész'&&order.completion_snapshot&&!order.completion_snapshot.signature&&<button className="btn primary big" onClick={()=>onComplete(order.completion_snapshot)}>Ügyfél aláírása</button>}
    {order.status==='lezárva'&&<button className="btn secondary big" onClick={onSignedPdf}>Aláírt PDF megnyitása</button>}
  </section></main>
}
