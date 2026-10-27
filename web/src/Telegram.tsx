import React, {useCallback, useEffect, useRef, useState} from 'react';

type Request = (path:string, body?:unknown, signal?:AbortSignal)=>Promise<unknown>;
type SavedRequest = {id:string; state:'NEEDS_PLANNING'; text:string};

function record(value:unknown):value is Record<string, unknown>{
 return typeof value==='object'&&value!==null&&!Array.isArray(value);
}

function savedRequests(status:unknown, inbox:unknown):SavedRequest[]{
 // This client supports the current disabled integration, never infers live readiness.
 if(!record(status)||status.mode!=='disabled'||status.live_connected!==false||status.voice_enabled!==false
   ||!record(inbox)||inbox.ai_planning_connected!==false||!Array.isArray(inbox.requests)||inbox.requests.length>50)
  throw new Error('unsupported_telegram_state');
 const ids=new Set<string>();
 return inbox.requests.map((item:unknown)=>{
  if(!record(item)||typeof item.id!=='string'||!item.id||item.id.length>100||ids.has(item.id)
    ||item.state!=='NEEDS_PLANNING'||typeof item.text!=='string'||item.text.length>2000)
   throw new Error('invalid_telegram_request');
  ids.add(item.id);
  return {id:item.id,state:'NEEDS_PLANNING',text:item.text};
 });
}

export function TelegramPanel({request}:{request:Request}){
 const [rows,setRows]=useState<SavedRequest[]|null>(null);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState(false);
 const sequence=useRef(0);
 const active=useRef<AbortController|null>(null);
 const reload=useCallback(async()=>{
  const current=++sequence.current;
  active.current?.abort();
  const controller=new AbortController(); active.current=controller;
  setLoading(true);setError(false);setRows(null);
  const timeout=window.setTimeout(()=>controller.abort(),10000);
  try{
   const [status,inbox]=await Promise.all([
    request('telegram/status',undefined,controller.signal),
    request('telegram/requests',undefined,controller.signal)
   ]);
   const next=savedRequests(status,inbox);
   if(current===sequence.current)setRows(next);
  }catch{
   if(current===sequence.current){setRows(null);setError(true)}
  }finally{
   window.clearTimeout(timeout);controller.abort();
   if(current===sequence.current)setLoading(false);
  }
 },[request]);
 useEffect(()=>{void reload();return()=>{++sequence.current;active.current?.abort()}},[reload]);
 return <section className="telegram-panel" aria-labelledby="telegram-heading" aria-busy={loading}>
  <h2 id="telegram-heading">Telegram</h2>
  {loading&&<p role="status">Загружаем состояние Telegram…</p>}
  {error&&<p role="alert">Раздел Telegram недоступен. Проверьте вход владельца и повторите загрузку. Остальная панель работает отдельно.</p>}
  {rows!==null&&<>
   <p>Бот не подключён.</p>
   <p>Пока проверен только тестовый обмен сообщениями. Голос и AI-планирование не подключены.</p>
   <h3>Сохранённые запросы</h3>
   {rows.length===0?<p>Сохранённых запросов пока нет.</p>:<>
    {rows.length===50&&<p>Показаны последние 50 запросов.</p>}
    <ul className="telegram-requests">{rows.map(row=><li key={row.id}>
     <p className="telegram-request-text">{row.text}</p>
     <p>Ожидает планирования. Выполнение не запускалось.</p>
    </li>)}</ul>
   </>}
  </>}
  <button disabled={loading} onClick={()=>void reload()}>Обновить Telegram</button>
 </section>
}
