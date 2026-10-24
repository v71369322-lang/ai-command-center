import React, {useState, useRef, useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';
import {IntegrationOverview, ExternalTaskPanel, type Integration} from './Integration';
type Draft = {title:string; mode:string; published:boolean; base_sha:string; head_sha:string; diff:string; risks:string[]; url:string|null};
type Coding = {stage?:string; plan?:string[]; summary?:string; failure?:string; test_runs?:{attempt:number;checks:{passed:boolean;tests_run:number;failures:number}}[];pr?:Draft};
type Task = {id:string; state:string; version:number; fence:number; attempts:number; payload_hash:string; artifact:string|null; artifact_hash:string|null; reason:string|null; payload:unknown;coding?:Coding;integration?:Integration};
type State = {epoch:number;checkpoint_digest:string;halted:boolean; recovery:boolean; tasks:Task[]; integration?:Integration; events:unknown[]; budget:Record<string, unknown>};
function App(){
 const [token,setToken]=useState(''); const [state,setState]=useState<State|null>(null);
 const [error,setError]=useState(''); const [health,setHealth]=useState<unknown>(null);
 const [mode,setMode]=useState('synthetic'); const [csrf,setCsrf]=useState('');
 const [draft,setDraft]=useState<Draft|null>(null);
 const generation=useRef(0);
 useEffect(()=>{fetch('/api/auth/mode').then(r=>r.json()).then(v=>setMode(v.mode)).catch(()=>setMode('unknown'))},[]);
 async function request(path:string,body?:unknown){
  const res=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:{...(mode==='synthetic'?{Authorization:'Bearer '+token}:{}),'X-CSRF-Token':csrf,'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await res.json(); if(!res.ok)throw new Error(data.detail||'Запрос отклонён'); return data;
 }
 async function refresh(){const current=generation.current;try{const next=await request('state');const status=await request('health');const proof=mode==='oidc'&&!csrf?await request('auth/csrf'):null;if(current===generation.current){setState(next);setHealth(status);if(proof)setCsrf(proof.csrf_token);setError('')}}catch(e){if(current===generation.current){setError(String(e));setState(null)}}}
 async function exchange(){try{const result=await request('auth/exchange',{assertion:token});generation.current++;setToken('');setCsrf(result.csrf_token);setError('Сессия создана. Обновите состояние.')}catch(e){setError(String(e))}}
 async function logout(){generation.current++;setToken('');setState(null);setHealth(null);setDraft(null);if(mode==='oidc'){try{await request('auth/logout',{})}catch{setError('Серверный отзыв не подтверждён; сессия может оставаться активной.')}}setCsrf('')}
 async function action(path:string,body:unknown={}){const current=generation.current;try{await request(path,body);if(current===generation.current)await refresh()}catch(e){if(current===generation.current)setError(String(e))}}
 async function openDraft(id:string){const current=generation.current;try{const value=await request(`tasks/${id}/pull-request`);if(current===generation.current)setDraft(value)}catch(e){if(current===generation.current)setError(String(e))}}
 const active=Boolean(state?.tasks.some(t=>['READY','RUNNING','CANCEL_REQUESTED'].includes(t.state)));
 useEffect(()=>{if(!active)return;const timer=setInterval(()=>{void refresh()},3000);return()=>clearInterval(timer)},[active,token,csrf,mode]);
 return <main><header><p className="label">AI COMMAND CENTER</p><h1>Тестовый контур F1</h1><p>Только синтетические данные. Не полный MVP.</p></header>
 <section><h2>Закрытый доступ</h2><label>{mode==='synthetic'?'Тестовый credential':'Подписанное MFA-подтверждение тестового IdP'}<input type="password" autoComplete="off" value={token} onChange={e=>{generation.current++;setToken(e.target.value);setState(null);setHealth(null);setDraft(null)}}/></label><p>{mode==='synthetic'?'Только синтетическая аутентификация. Реальная MFA не подтверждена.':'Адаптер IdP. Реальный провайдер и production-доступ ещё не подключены.'}</p>{mode==='oidc'&&<button onClick={exchange}>Создать защищённую сессию</button>}<button onClick={refresh}>Войти / обновить</button><button onClick={logout}>Выйти</button></section>
 {error&&<p role="alert" className="error">{error}</p>}
 {draft&&state&&<section><h2>Подготовленный PR</h2><h3>{draft.title}</h3><p>{draft.published&&draft.mode==='github'?'GitHub draft PR создан.':draft.mode==='http_mock'?'HTTP-mock: внешний сценарий проверен без реального AI и GitHub PR.':'Mock-режим: PR не опубликован в GitHub. Реальный AI не подключён.'}</p><ul>{draft.risks.map(r=><li key={r}>{r}</li>)}</ul><details><summary>Изменения и доказательства</summary><p className="id">Исходный commit: {draft.base_sha}</p><p className="id">Результат: {draft.head_sha}</p><pre>{draft.diff}</pre></details><button onClick={()=>setDraft(null)}>Закрыть PR</button></section>}
 {state&&<><section><h2>Управление</h2><p>{state.halted?'Запуски остановлены':state.recovery?'Требуется сверка восстановления':'Контур допускает синтетические задачи'}</p>
 <button onClick={()=>action('simulator/commands',{kind:'render',values:{message:'synthetic only'}})}>Создать безопасную задачу</button>
 <button onClick={()=>action('simulator/commands',{kind:'approved_render',values:{message:'approval fixture'}})}>Создать задачу с подтверждением</button>
 <h3>Тестовый разработчик F2</h3><p>Исправит сумму положительных чисел в отдельном синтетическом репозитории. До двух попыток, затем независимая проверка. Provider: mock, настоящий AI не подключён.</p><button onClick={()=>action('coding/tasks',{})}>Запустить тестового разработчика</button>
 {state.halted&&!state.recovery&&<button onClick={()=>action("control/resume",{epoch:state.epoch,checkpoint_digest:state.checkpoint_digest})}>Снять обычную остановку для новых задач</button>}<button className="danger" onClick={()=>action('control/stop')}>Аварийная остановка</button><pre>{JSON.stringify(health,null,2)}</pre><h3>Синтетический бюджет</h3><pre>{JSON.stringify(state.budget,null,2)}</pre></section>
 <IntegrationOverview value={state.integration} create={()=>action('coding/tasks',{provider:'openai'})}/><h2>Задачи и результаты</h2>{state.tasks.map(t=><section key={t.id} id={'task-'+t.id}><h3>{t.state}</h3><ExternalTaskPanel task={t} authorize={(id,version,nanos)=>action(`coding/tasks/${id}/authorize`,{version,budget_nano_rub:nanos,seconds:120})}/>{t.coding?.stage&&<><p>{t.state==='CANCELLED'?'Задача остановлена. Результат не принят.':t.coding.summary}</p><details><summary>План выполнения</summary><ol>{t.coding.plan?.map(p=><li key={p}>{p}</li>)}</ol></details>{t.coding.test_runs?.map(r=><p key={r.attempt}>Проверка {r.attempt}: {r.checks.passed?'пройдена':'найдена ошибка'}</p>)}{t.state==='SUCCEEDED'&&t.coding.pr&&<button onClick={()=>openDraft(t.id)}>Открыть подготовленный PR</button>}</>}<details><summary>Технические доказательства</summary><p className="id">{t.id}</p><p>Версия {t.version} · попытка {t.attempts} · fence {t.fence}</p><p className="id">Параметры: {t.payload_hash}</p><pre>{JSON.stringify(t.payload,null,2)}</pre></details>{t.reason&&<p>{t.reason}</p>}
 {t.state==='WAITING_APPROVAL'&&!t.integration&&<><p>Риск: только синтетические файлы изолированного запуска, внешних действий нет. Согласование: точная версия {t.version}, действие — синтетический render, срок 120 секунд.</p><button onClick={()=>action(`tasks/${t.id}/approve`,{version:t.version,seconds:120})}>Подтвердить эту версию</button></>}
 <button onClick={()=>action(`tasks/${t.id}/cancel`)}>Отказать / отменить</button><button onClick={()=>action(`tasks/${t.id}/revoke`)}>Отозвать подтверждение</button>
 {t.state==='FAILED'&&<button onClick={()=>action(`tasks/${t.id}/retry`)}>Запросить безопасный повтор</button>}
 {t.artifact&&<><pre>{t.artifact}</pre><p className="id">SHA-256: {t.artifact_hash}</p></>}</section>)}
 <section><h2>История и инциденты</h2><pre>{JSON.stringify(state.events,null,2)}</pre></section></>}
 </main>
}
createRoot(document.getElementById('root')!).render(<App/>);
