import React, {useCallback, useEffect, useRef, useState} from 'react';

type Request = (path:string, body?:unknown, signal?:AbortSignal)=>Promise<unknown>;
type SavedRequest = {id:string; state:'NEEDS_PLANNING'; text:string};
type Connection = {mode:'disabled'|'live'|'http_mock';status:string;live_connected:boolean};

function record(value:unknown):value is Record<string, unknown>{
 return typeof value==='object'&&value!==null&&!Array.isArray(value);
}

function connection(status:unknown):Connection{
 if(!record(status)||!['disabled','live','http_mock'].includes(String(status.mode))||status.voice_enabled!==false
   ||!['disabled','waiting','stale','stopped','degraded','polling'].includes(String(status.status))
   ||typeof status.live_connected!=='boolean'
   ||status.live_connected!==(status.mode==='live'&&status.status==='polling')
   ||(status.mode==='disabled')!==(status.status==='disabled'))throw new Error('unsupported_telegram_state');
 return status as Connection;
}

function savedRequests(inbox:unknown):SavedRequest[]{
 if(!record(inbox)||inbox.ai_planning_connected!==false||!Array.isArray(inbox.requests)||inbox.requests.length>50)
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
 const [state,setState]=useState<Connection|null>(null);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState(false);
 const sequence=useRef(0);
 const active=useRef<AbortController|null>(null);
 const reload=useCallback(async()=>{
  const current=++sequence.current;
  active.current?.abort();
  const controller=new AbortController(); active.current=controller;
  setLoading(true);setError(false);setRows(null);setState(null);
  const timeout=window.setTimeout(()=>controller.abort(),10000);
  try{
   const [status,inbox]=await Promise.all([
    request('telegram/status',undefined,controller.signal),
    request('telegram/requests',undefined,controller.signal)
   ]);
   const currentState=connection(status);
   const next=savedRequests(inbox);
   if(current===sequence.current){setRows(next);setState(currentState)}
  }catch{
   if(current===sequence.current){setRows(null);setState(null);setError(true)}
  }finally{
   window.clearTimeout(timeout);controller.abort();
   if(current===sequence.current)setLoading(false);
  }
 },[request]);
 useEffect(()=>{void reload();const timer=window.setInterval(()=>void reload(),15000);return()=>{window.clearInterval(timer);++sequence.current;active.current?.abort()}},[reload]);
 return <section className="telegram-panel" aria-labelledby="telegram-heading" aria-busy={loading}>
  <h2 id="telegram-heading">Telegram</h2>
  {loading&&<p role="status">Загружаем состояние Telegram…</p>}
  {error&&<p role="alert">Раздел Telegram недоступен. Проверьте вход владельца и повторите загрузку. Остальная панель работает отдельно.</p>}
  {rows!==null&&<>
   <p role="status">{state?.mode==='disabled'?'Бот не подключён.':state?.mode==='http_mock'?'Тестовый HTTP-адаптер. Настоящий бот не подключён.':state?.live_connected?'Бот подключён; обработчик получает сообщения.':state?.status==='stale'?'Нет свежего подтверждения работы бота.':state?.status==='degraded'?'Ошибка связи с Telegram.':state?.status==='stopped'?'Обработчик Telegram остановлен.':'Ожидаем подтверждение работы обработчика.'}</p>
   <p>Голос и AI-планирование не подключены.</p>
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
