import React, { useEffect, useState } from 'react'
import { api, downloadFile } from '../api.js'
import DataTable from '../components/DataTable.jsx'

const today = new Date().toISOString().slice(0,10)
const first = `${today.slice(0,8)}01`
export default function ServiceReports(){
  const [dateFrom,setDateFrom]=useState(first),[dateTo,setDateTo]=useState(today),[data,setData]=useState(null),[error,setError]=useState('')
  async function load(){ try{setData(await api(`/reports/service?date_from=${dateFrom}&date_to=${dateTo}`));setError('')}catch(e){setError(e.message)} }
  useEffect(()=>{load()},[])
  return <section><div className="page-head"><div><h1>Szerviz riportok</h1><p className="muted">Munkalapterhelés, lezárások és munkaórák időszak szerint.</p></div><div className="inline-actions"><input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)}/><input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)}/><button onClick={load}>Frissítés</button><button className="secondary" onClick={()=>downloadFile(`/reports/service.csv?date_from=${dateFrom}&date_to=${dateTo}`)}>CSV export</button></div></div>{error&&<div className="error">{error}</div>}{data&&<><div className="report-stat-grid"><div className="report-stat"><span>Munkalapok</span><strong>{data.work_order_count}</strong></div><div className="report-stat"><span>Lezárt</span><strong>{data.closed_count}</strong></div><div className="report-stat"><span>Sürgős</span><strong>{data.urgent_count}</strong></div><div className="report-stat"><span>Munkaóra</span><strong>{Number(data.labor_hours||0).toLocaleString('hu-HU')}</strong></div></div><div className="report-grid"><div className="panel"><h2>Státusz szerint</h2>{Object.entries(data.by_status||{}).map(([k,v])=><div className="report-line" key={k}><span>{k}</span><strong>{v}</strong></div>)}</div><div className="panel"><h2>Munka típusa szerint</h2>{Object.entries(data.by_work_type||{}).map(([k,v])=><div className="report-line" key={k}><span>{k}</span><strong>{v}</strong></div>)}</div></div><div className="panel"><h2>Technikusi terhelés</h2><DataTable rows={data.by_technician||[]} columns={[{key:'technician_name',label:'Technikus'},{key:'work_order_count',label:'Munkalap'},{key:'closed_count',label:'Lezárt'},{key:'labor_hours',label:'Munkaóra',render:r=>Number(r.labor_hours||0).toLocaleString('hu-HU')}]} /></div></>}</section>
}
