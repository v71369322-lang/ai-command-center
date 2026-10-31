import React, {useCallback, useEffect, useRef, useState} from 'react';

type Request=(path:string,body?:unknown,signal?:AbortSignal)=>Promise<unknown>;
type Item={code:string;level:'critical'|'warning'|'info';count:number;label:string};
type View={items:Item[];total_pending_requests:number;task_admission_halted:boolean;recovery:boolean;reminders_connected:false;ai_planning_connected:false};
function record(value:unknown):value is Record<string,unknown>{return typeof value==='object'&&value!==null&&!Array.isArray(value)}
function parse(value:unknown):View{
 if(!record(value)||value.schema!==1||!Array.isArray(value.items)||value.items.length>8
  ||!Number.isInteger(value.total_pending_requests)||Number(value.total_pending_requests)<0
  ||typeof value.task_admission_halted!=='boolean'||typeof value.recovery!=='boolean'
  ||value.reminders_connected!==false||value.ai_planning_connected!==false||value.execution_started!==false)throw new Error();
 const seen=new Set<string>();
 const items=value.items.map(raw=>{
  if(!record(raw)||typeof raw.code!=='string'||!/^[A-Z_]{3,40}$/.test(raw.code)||seen.has(raw.code)
   ||!['critical','warning','info'].includes(String(raw.level))||!Number.isInteger(raw.count)||Number(raw.count)<1
   ||typeof raw.label!=='string'||!raw.label||raw.label.length>100)throw new Error();
  seen.add(raw.code);return {code:raw.code,level:raw.level as Item['level'],count:Number(raw.count),label:raw.label};
 });
 return {items,total_pending_requests:Number(value.total_pending_requests),task_admission_halted:value.task_admission_halted,
  recovery:value.recovery,reminders_connected:false,ai_planning_connected:false};
}

export function AttentionCenter({request}:{request:Request}){
 const [view,setView]=useState<View|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 const generation=useRef(0),active=useRef<AbortController|null>(null);
 const reload=useCallback(async()=>{const current=++generation.current;active.current?.abort();const controller=new AbortController();active.current=controller;
  setLoading(true);setError('');const timer=window.setTimeout(()=>controller.abort(),10000);
  try{const next=parse(await request('attention',undefined,controller.signal));if(current===generation.current)setView(next)}
  catch{if(current===generation.current){setView(null);setError('Сводка внимания недоступна. Остальные разделы работают отдельно.')}}
  finally{window.clearTimeout(timer);controller.abort();if(current===generation.current)setLoading(false)}},[request]);
 useEffect(()=>{void reload();return()=>{++generation.current;active.current?.abort()}},[reload]);
 return <section aria-labelledby="attention-heading" aria-busy={loading}>
  <h2 id="attention-heading">Центр внимания</h2>
  <p>Показывает незакрытые решения и очереди. Просмотр ничего не запускает.</p>
  {loading&&<p role="status">Собираем сводку…</p>}{error&&<p role="alert">{error}</p>}
  {view&&<>{view.items.length?<ul>{view.items.map(item=><li key={item.code}><strong>{item.count}</strong> · {item.label}</li>)}</ul>:<p>Пунктов, требующих внимания, сейчас нет.</p>}
   <p>Автоматические напоминания ещё не подключены. AI-планирование запросов ещё не подключено.</p>
   <button disabled={loading} onClick={()=>void reload()}>Обновить сводку</button></>}
 </section>;
}
