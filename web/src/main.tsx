import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
type Task = {id:string; state:string; version:number; fence:number; attempts:number; payload_hash:string; artifact:string|null; artifact_hash:string|null; reason:string|null; payload:unknown};
type State = {epoch:number;checkpoint_digest:string;halted:boolean; recovery:boolean; tasks:Task[]; events:unknown[]; budget:Record<string, unknown>};
function App(){
 const [token,setToken]=useState(''); const [state,setState]=useState<State|null>(null);
 const [error,setError]=useState(''); const [health,setHealth]=useState<unknown>(null);
 async function request(path:string,body?:unknown){
  const res=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await res.json(); if(!res.ok)throw new Error(data.detail||'Запрос отклонён'); return data;
 }
 async function refresh(){try{setState(await request('state'));setHealth(await request('health'));setError('')}catch(e){setError(String(e));setState(null)}}
 async function action(path:string,body:unknown={}){try{await request(path,body);await refresh()}catch(e){setError(String(e))}}
 return <main><header><p className="label">AI COMMAND CENTER</p><h1>Тестовый контур F1</h1><p>Только синтетические данные. Не полный MVP.</p></header>
 <section><h2>Закрытый доступ</h2><label>Тестовый credential<input type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)}/></label><p>Credential хранится только в памяти страницы. Реальная MFA здесь не подтверждена.</p><button onClick={refresh}>Войти / обновить</button><button onClick={()=>{setToken('');setState(null);setHealth(null)}}>Выйти</button></section>
 {error&&<p role="alert" className="error">{error}</p>}
 {state&&<><section><h2>Управление</h2><p>{state.halted?'Запуски остановлены':state.recovery?'Требуется сверка восстановления':'Контур допускает синтетические задачи'}</p>
 <button onClick={()=>action('simulator/commands',{kind:'render',values:{message:'synthetic only'}})}>Создать безопасную задачу</button>
 <button onClick={()=>action('simulator/commands',{kind:'approved_render',values:{message:'approval fixture'}})}>Создать задачу с подтверждением</button>
 {state.halted&&!state.recovery&&<button onClick={()=>action("control/resume",{epoch:state.epoch,checkpoint_digest:state.checkpoint_digest})}>Снять обычную остановку для новых задач</button>}<button className="danger" onClick={()=>action('control/stop')}>Аварийная остановка</button><pre>{JSON.stringify(health,null,2)}</pre><h3>Синтетический бюджет</h3><pre>{JSON.stringify(state.budget,null,2)}</pre></section>
 <h2>Задачи и результаты</h2>{state.tasks.map(t=><section key={t.id}><h3>{t.state}</h3><p className="id">{t.id}</p><p>Версия {t.version} · попытка {t.attempts} · fence {t.fence}</p><p className="id">Параметры: {t.payload_hash}</p><pre>{JSON.stringify(t.payload,null,2)}</pre>{t.reason&&<p>{t.reason}</p>}
 {t.state==='WAITING_APPROVAL'&&<><p>Риск: только синтетические файлы изолированного запуска, внешних действий нет. Согласование: точная версия {t.version}, действие — синтетический render, срок 120 секунд.</p><button onClick={()=>action(`tasks/${t.id}/approve`,{version:t.version,seconds:120})}>Подтвердить эту версию</button></>}
 <button onClick={()=>action(`tasks/${t.id}/cancel`)}>Отказать / отменить</button><button onClick={()=>action(`tasks/${t.id}/revoke`)}>Отозвать подтверждение</button>
 {t.state==='FAILED'&&<button onClick={()=>action(`tasks/${t.id}/retry`)}>Запросить безопасный повтор</button>}
 {t.artifact&&<><pre>{t.artifact}</pre><p className="id">SHA-256: {t.artifact_hash}</p></>}</section>)}
 <section><h2>История и инциденты</h2><pre>{JSON.stringify(state.events,null,2)}</pre></section></>}
 </main>
}
createRoot(document.getElementById('root')!).render(<App/>);
