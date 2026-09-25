import { useEffect, useState } from 'react'
import LoginScreen from './components/LoginScreen.jsx'
import MfaScreen from './components/MfaScreen.jsx'
import WorkOrderList from './components/WorkOrderList.jsx'
import WorkOrderDetail from './components/WorkOrderDetail.jsx'
import CompletionForm from './components/CompletionForm.jsx'
import SignScreen from './components/SignScreen.jsx'
import { apiBlob, apiFetch } from './services/api.js'
import { login, logout, restoreSession, verifyMfa } from './services/auth.js'
import { openOrSharePdf } from './services/files.js'
import { disablePushNotifications, initializePushNotifications } from './services/push.js'

export default function App(){
  const [screen,setScreen]=useState('boot');const[me,setMe]=useState(null);const[config,setConfig]=useState(null);const[orders,setOrders]=useState([]);const[order,setOrder]=useState(null);const[snapshot,setSnapshot]=useState(null);const[challenge,setChallenge]=useState(null);const[busy,setBusy]=useState(false);const[error,setError]=useState('');const[pushNotice,setPushNotice]=useState('')
  async function loadIdentity(){const [who,cfg]=await Promise.all([apiFetch('/me'),apiFetch('/config')]);setMe(who);setConfig(cfg)}
  async function loadToday(){setBusy(true);try{setOrders(await apiFetch('/work-orders/today'));setError('')}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function loadOrder(id=order?.id){if(!id)return;setBusy(true);try{setOrder(await apiFetch(`/work-orders/${id}`));setError('')}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function enablePush(){try{await initializePushNotifications({onOpenWorkOrder:async id=>{await loadOrder(id);setScreen('detail')},onForeground:n=>{setPushNotice(n?.title || 'Új munkalap értesítés');setTimeout(()=>setPushNotice(''),5000)}})}catch(e){console.warn('Push init failed',e)}}
  useEffect(()=>{(async()=>{if(await restoreSession()){try{await loadIdentity();await loadToday();setScreen('list');enablePush();return}catch{}}setScreen('login')})()},[])
  async function handleLogin(email,password){setBusy(true);setError('');try{const result=await login(email,password);if(result.mfa_setup_required){setError('A mobil használat előtt a webes felületen be kell állítani az MFA-t.');return}if(result.mfa_required){setChallenge(result.challenge_token);setScreen('mfa');return}await loadIdentity();await loadToday();setScreen('list');enablePush()}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function handleMfa(code){setBusy(true);setError('');try{await verifyMfa(challenge,code);setChallenge(null);await loadIdentity();await loadToday();setScreen('list');enablePush()}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function openOrder(id){await loadOrder(id);setScreen('detail')}
  async function handleLogout(){await disablePushNotifications();await logout();setMe(null);setOrders([]);setOrder(null);setScreen('login')}
  async function signedPdf(){try{const blob=await apiBlob(`/work-orders/${order.id}/signed-pdf`);await openOrSharePdf(blob,`${order.number}-signed.pdf`)}catch(e){setError(e.message)}}
  if(screen==='boot')return <main className="splash">Munkalap</main>
  if(screen==='login')return <LoginScreen onLogin={handleLogin} busy={busy} error={error}/>
  if(screen==='mfa')return <MfaScreen onVerify={handleMfa} onCancel={()=>{setChallenge(null);setError('');setScreen('login')}} busy={busy} error={error}/>
  if(screen==='list')return <>{pushNotice&&<div className="push-banner">{pushNotice}</div>}<WorkOrderList orders={orders} onOpen={openOrder} onRefresh={loadToday} loading={busy} me={me} onLogout={handleLogout}/>{error&&<div className="floating-error">{error}</div>}</>
  if(screen==='detail'&&order)return <WorkOrderDetail order={order} api={apiFetch} onBack={()=>{setScreen('list');loadToday()}} onReload={()=>loadOrder(order.id)} onComplete={(existing)=>{if(existing?.id){setSnapshot(existing);setScreen('sign')}else setScreen('complete')}} onSignedPdf={signedPdf}/>
  if(screen==='complete'&&order)return <CompletionForm order={order} api={apiFetch} onCancel={()=>setScreen('detail')} onCompleted={async snap=>{setSnapshot(snap);await loadOrder(order.id);setScreen('sign')}}/>
  if(screen==='sign'&&order&&snapshot)return <SignScreen order={order} snapshot={snapshot} config={config} api={apiFetch} onCancel={()=>setScreen('detail')} onSigned={async()=>{await loadOrder(order.id);setScreen('detail')}}/>
  return <main className="splash">Állapot visszaállítása…</main>
}
