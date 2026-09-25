import { useRef, useState } from 'react'
import SignaturePad from './SignaturePad.jsx'

export default function SignScreen({ order, snapshot, config, api, onSigned, onCancel }) {
  const pad=useRef(null); const [name,setName]=useState(''); const [role,setRole]=useState(''); const [accepted,setAccepted]=useState(false); const [busy,setBusy]=useState(false); const [error,setError]=useState('')
  const s=snapshot?.snapshot||{}
  async function sign(e){e.preventDefault();setError('');if(!accepted)return setError('Az elfogadó nyilatkozatot el kell fogadni.');if(!pad.current?.hasInk())return setError('Az ügyfél aláírása hiányzik.');setBusy(true);try{const blob=await pad.current.toBlob();const form=new FormData();form.append('snapshot_id',String(snapshot.id));form.append('signer_name',name.trim());if(role.trim())form.append('signer_role',role.trim());form.append('signature',new File([blob],'signature.png',{type:'image/png'}));const result=await api(`/work-orders/${order.id}/signature`,{method:'POST',body:form});onSigned(result)}catch(e){setError(e.message)}finally{setBusy(false)}}
  return <main><header className="app-header"><button className="icon-btn" onClick={onCancel}>‹ Vissza</button><strong>Ügyfél aláírása</strong><span/></header><form className="page stack" onSubmit={sign}>
    <section className="summary-card"><h2>{s.customer?.name||order.customer_name}</h2><p>{s.location?.address||order.location_address||order.customer_address}</p><div className="kv"><span>Munkalap</span><strong>{order.number}</strong><span>Elvégzett munka</span><strong>{s.work_done||order.work_done||'–'}</strong><span>Fotók</span><strong>{s.photos?.length||0} db</strong><span>Snapshot</span><code>{snapshot.snapshot_sha256?.slice(0,16)}…</code></div></section>
    <label>Aláíró neve *<input required minLength="2" value={name} onChange={e=>setName(e.target.value)} /></label><label>Beosztás / szerepkör<input value={role} onChange={e=>setRole(e.target.value)} /></label>
    <div className="acceptance"><label className="check"><input type="checkbox" checked={accepted} onChange={e=>setAccepted(e.target.checked)}/><span>{config?.acceptance_text||'A munkalapon feltüntetett munkavégzést és adatokat megismertem.'}</span></label><small>Nyilatkozat verzió: {config?.acceptance_text_version||'–'}</small></div>
    <label>Aláírás *</label><SignaturePad ref={pad}/>{error&&<div className="error-box">{error}</div>}<button className="btn primary" disabled={busy}>{busy?'Lezárás…':'Aláírás és munkalap lezárása'}</button>
  </form></main>
}
