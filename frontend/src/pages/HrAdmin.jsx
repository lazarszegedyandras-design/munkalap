import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import DataTable from '../components/DataTable.jsx'
import { Field } from '../components/FormField.jsx'

const currentYear = new Date().getFullYear()
const emptyProfile = { employee_number:'', company_code:'', organizational_unit:'', job_title:'', manager_user_id:'', leave_approver_user_id:'', employment_start_date:'', employment_end_date:'', active:true }
const emptyEntitlement = { base_days:'', child_days:'0', sick_leave_days:'0', carried_days:'0', adjustment_days:'0', note:'' }
const importStatusLabel = { pending:'Párosításra vár', ambiguous:'Kézi párosítás kell', conflict:'Ütközés', applied:'Betöltve' }

export default function HrAdmin() {
  const [year,setYear]=useState(currentYear), [rows,setRows]=useState([]), [calendar,setCalendar]=useState([]), [imports,setImports]=useState([])
  const [selectedId,setSelectedId]=useState(null), [profile,setProfile]=useState(emptyProfile), [entitlement,setEntitlement]=useState(emptyEntitlement)
  const [calendarForm,setCalendarForm]=useState({calendar_date:'',is_working_day:false,label:''}), [error,setError]=useState('')
  const selected = rows.find(r=>r.user.id===selectedId)
  const users = useMemo(()=>rows.map(r=>r.user),[rows])
  const approverUsers = useMemo(()=>users.filter(u=>u.can_approve_leave),[users])

  useEffect(()=>{ load() },[year])
  async function load(){
    try {
      const [employees,days,importRows]=await Promise.all([
        api(`/hr/admin/employees?year=${year}`), api(`/hr/admin/calendar?year=${year}`), api(`/hr/admin/imported-leave?year=${year}`)
      ])
      setRows(employees); setCalendar(days); setImports(importRows); setError('')
    } catch(e){setError(e.message)}
  }
  function edit(row){
    setSelectedId(row.user.id)
    setProfile(row.profile ? {
      employee_number:row.profile.employee_number||'', company_code:row.profile.company_code||'', organizational_unit:row.profile.organizational_unit||'', job_title:row.profile.job_title||'',
      manager_user_id:row.profile.manager_user_id||'', leave_approver_user_id:row.profile.leave_approver_user_id||'', employment_start_date:row.profile.employment_start_date||'', employment_end_date:row.profile.employment_end_date||'', active:row.profile.active,
    } : emptyProfile)
    setEntitlement(row.entitlement ? {
      base_days:String(row.entitlement.base_days), child_days:String(row.entitlement.child_days||0), sick_leave_days:String(row.entitlement.sick_leave_days||0),
      carried_days:String(row.entitlement.carried_days), adjustment_days:String(row.entitlement.adjustment_days), note:row.entitlement.note||''
    } : emptyEntitlement)
  }
  async function saveProfile(e){
    e.preventDefault(); if(!selectedId)return
    const body={...profile,manager_user_id:profile.manager_user_id?Number(profile.manager_user_id):null,leave_approver_user_id:profile.leave_approver_user_id?Number(profile.leave_approver_user_id):null,employment_start_date:profile.employment_start_date||null,employment_end_date:profile.employment_end_date||null}
    try{await api(`/hr/admin/employees/${selectedId}/profile`,{method:'PUT',body});await load()}catch(e){setError(e.message)}
  }
  async function saveEntitlement(e){
    e.preventDefault(); if(!selectedId)return
    try{await api(`/hr/admin/employees/${selectedId}/entitlement`,{method:'PUT',body:{year,base_days:Number(entitlement.base_days||0),child_days:Number(entitlement.child_days||0),sick_leave_days:Number(entitlement.sick_leave_days||0),carried_days:Number(entitlement.carried_days||0),adjustment_days:Number(entitlement.adjustment_days||0),note:entitlement.note||null}});await load()}catch(e){setError(e.message)}
  }
  async function saveCalendar(e){
    e.preventDefault(); try{await api('/hr/admin/calendar',{method:'PUT',body:calendarForm});setCalendarForm({calendar_date:'',is_working_day:false,label:''});await load()}catch(e){setError(e.message)}
  }
  async function removeCalendar(row){try{await api(`/hr/admin/calendar/${row.calendar_date}`,{method:'DELETE'});await load()}catch(e){setError(e.message)}}
  async function autoLink(){try{await api('/hr/admin/imported-leave/auto-link',{method:'POST'});await load()}catch(e){setError(e.message)}}
  async function linkImport(row,userId){
    if(!userId)return
    const user=users.find(u=>u.id===Number(userId))
    if(!confirm(`A(z) ${row.full_name} RLB adatokat ehhez a felhasználóhoz rendeled: ${user?.full_name || userId}?`))return
    try{await api(`/hr/admin/imported-leave/${row.id}/link`,{method:'POST',body:{user_id:Number(userId),allow_merge:false}});await load()}catch(e){setError(e.message)}
  }

  return <section>
    <div className="page-head"><div><h1>HR adminisztráció</h1><p className="muted">Munkavállalói profilok, jóváhagyók, éves szabadságkeretek, forrásimportok és munkanaptár-kivételek.</p></div><Field label="Év"><select value={year} onChange={e=>setYear(Number(e.target.value))}>{[currentYear-1,currentYear,currentYear+1].map(y=><option key={y}>{y}</option>)}</select></Field></div>
    {error && <div className="error">{error}</div>}

    {year===2026 && <div className="panel"><div className="page-head"><div><h2>Importált 2026. évi RLB szabadságadatok</h2><p className="muted">A programba csomagolt forrásadatok automatikusan csak egyértelmű, konfliktusmentes felhasználóhoz kerülnek. A párosítatlan rekord kézzel rendelhető felhasználóhoz.</p></div><button className="secondary" onClick={autoLink}>Automatikus párosítás újrafuttatása</button></div>
      <DataTable rows={imports} columns={[
        {key:'full_name',label:'Forrásnév'}, {key:'employee_number',label:'Törzsszám'}, {key:'job_title',label:'Beosztás',render:r=>r.job_title||''},
        {key:'base_days',label:'Alap'}, {key:'child_days',label:'Gyermek után'}, {key:'annual_used_days',label:'Kiadott szabadság'},
        {key:'sick_leave_days',label:'Betegkeret'}, {key:'sick_used_days',label:'Kiadott betegszab.'},
        {key:'linked_user_name',label:'Párosított felhasználó',render:r=>r.linked_user_name||''},
        {key:'status',label:'Állapot',render:r=>importStatusLabel[r.status]||r.status}, {key:'status_message',label:'Megjegyzés',render:r=>r.status_message||''},
      ]} actions={row=>row.status==='applied'?null:<select defaultValue="" onChange={e=>linkImport(row,e.target.value)}><option value="">Párosítás…</option>{users.map(u=><option key={u.id} value={u.id}>{u.full_name}</option>)}</select>} />
    </div>}

    <div className="panel"><h2>Munkavállalók</h2>
      <DataTable rows={rows.map(row => ({ ...row, id: row.user.id }))} columns={[
        {key:'user.full_name',label:'Név'}, {key:'user.email',label:'Email'}, {key:'profile.employee_number',label:'Törzsszám',render:r=>r.profile?.employee_number||''},
        {key:'profile.job_title',label:'Beosztás',render:r=>r.profile?.job_title||''}, {key:'profile.organizational_unit',label:'Szervezeti egység',render:r=>r.profile?.organizational_unit||''}, {key:'profile.leave_approver.full_name',label:'Jóváhagyó',render:r=>r.profile?.leave_approver?.full_name||''},
        {key:'entitlement.total_days',label:`${year}. keret`,render:r=>r.entitlement?.total_days ?? ''},
      ]} actions={row=><button onClick={()=>edit(row)}>HR adatok</button>} />
    </div>

    {selected && <div className="hr-admin-grid">
      <div className="panel"><h2>HR profil – {selected.user.full_name}</h2><form className="grid-form" onSubmit={saveProfile}>
        <Field label="Törzsszám"><input value={profile.employee_number} onChange={e=>setProfile(p=>({...p,employee_number:e.target.value}))}/></Field>
        <Field label="Cégkód"><input value={profile.company_code} onChange={e=>setProfile(p=>({...p,company_code:e.target.value}))}/></Field>
        <Field label="Beosztás"><input value={profile.job_title} onChange={e=>setProfile(p=>({...p,job_title:e.target.value}))}/></Field>
        <Field label="Szervezeti egység"><input value={profile.organizational_unit} onChange={e=>setProfile(p=>({...p,organizational_unit:e.target.value}))}/></Field>
        <Field label="Vezető"><select value={profile.manager_user_id} onChange={e=>setProfile(p=>({...p,manager_user_id:e.target.value}))}><option value="">Nincs</option>{users.filter(u=>u.id!==selectedId).map(u=><option key={u.id} value={u.id}>{u.full_name}</option>)}</select></Field>
        <Field label="Szabadság-jóváhagyó"><select value={profile.leave_approver_user_id} onChange={e=>setProfile(p=>({...p,leave_approver_user_id:e.target.value}))}><option value="">Nincs</option>{approverUsers.filter(u=>u.id!==selectedId).map(u=><option key={u.id} value={u.id}>{u.full_name}</option>)}</select></Field>
        <Field label="Munkaviszony kezdete"><input type="date" value={profile.employment_start_date} onChange={e=>setProfile(p=>({...p,employment_start_date:e.target.value}))}/></Field>
        <Field label="Munkaviszony vége"><input type="date" value={profile.employment_end_date} onChange={e=>setProfile(p=>({...p,employment_end_date:e.target.value}))}/></Field>
        <label className="checkbox"><input type="checkbox" checked={profile.active} onChange={e=>setProfile(p=>({...p,active:e.target.checked}))}/> Aktív HR profil</label>
        <div className="form-actions"><button>Profil mentése</button></div>
      </form></div>
      <div className="panel"><h2>{year}. évi szabadságkeret</h2>{!selected.profile && <div className="notice">Előbb mentsd el a HR profilt.</div>}<form className="grid-form" onSubmit={saveEntitlement}>
        <Field label="Alapszabadság"><input type="number" step="0.5" min="0" value={entitlement.base_days} onChange={e=>setEntitlement(p=>({...p,base_days:e.target.value}))}/></Field>
        <Field label="Gyermekek után járó"><input type="number" step="0.5" min="0" value={entitlement.child_days} onChange={e=>setEntitlement(p=>({...p,child_days:e.target.value}))}/></Field>
        <Field label="Betegszabadság keret"><input type="number" step="0.5" min="0" value={entitlement.sick_leave_days} onChange={e=>setEntitlement(p=>({...p,sick_leave_days:e.target.value}))}/></Field>
        <Field label="Áthozott"><input type="number" step="0.5" min="0" value={entitlement.carried_days} onChange={e=>setEntitlement(p=>({...p,carried_days:e.target.value}))}/></Field>
        <Field label="Korrekció"><input type="number" step="0.5" value={entitlement.adjustment_days} onChange={e=>setEntitlement(p=>({...p,adjustment_days:e.target.value}))}/></Field>
        <Field label="Megjegyzés"><textarea value={entitlement.note} onChange={e=>setEntitlement(p=>({...p,note:e.target.value}))}/></Field>
        <div className="form-actions"><button disabled={!selected.profile}>Keret mentése</button></div>
      </form></div>
    </div>}

    <div className="panel"><h2>Munkanaptár-kivételek – {year}</h2><p className="muted">Alapesetben hétfő–péntek munkanap. Itt rögzíthető munkaszüneti hétköznap vagy áthelyezett szombati munkanap.</p>
      <form className="hr-calendar-form" onSubmit={saveCalendar}>
        <Field label="Dátum"><input type="date" required value={calendarForm.calendar_date} onChange={e=>setCalendarForm(p=>({...p,calendar_date:e.target.value}))}/></Field>
        <label className="checkbox"><input type="checkbox" checked={calendarForm.is_working_day} onChange={e=>setCalendarForm(p=>({...p,is_working_day:e.target.checked}))}/> Munkanap</label>
        <Field label="Megnevezés"><input value={calendarForm.label} onChange={e=>setCalendarForm(p=>({...p,label:e.target.value}))} placeholder="pl. ünnepnap / áthelyezett munkanap"/></Field>
        <button>Mentés</button>
      </form>
      <DataTable rows={calendar} columns={[{key:'calendar_date',label:'Dátum'},{key:'is_working_day',label:'Típus',render:r=>r.is_working_day?'Munkanap':'Nem munkanap'},{key:'label',label:'Megnevezés',render:r=>r.label||''}]} actions={row=><button className="danger" onClick={()=>removeCalendar(row)}>Törlés</button>}/>
    </div>
  </section>
}
