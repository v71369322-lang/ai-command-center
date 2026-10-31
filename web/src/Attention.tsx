import React, {useCallback, useEffect, useRef, useState} from 'react';

type Request=(path:string,body?:unknown,signal?:AbortSignal)=>Promise<unknown>;
type Item={code:string;level:'critical'|'warning'|'info';count:number;label:string;urgency:string;confidence:string;impact:string;target:'control-center'|'task-results'|'projects-heading'};
type Activity={sequence:number;slot:string;outcome:'queued'|'suppressed'|'critical';delivery_state:string|null;schedule_version:number;critical_quiet_bypass:boolean};
type DeliveryHealth={state:'never'|'pending'|'confirmed'|'uncertain'|'suppressed';action_required:boolean;last_slot:string|null};
type View={items:Item[];highest_level:'critical'|'warning'|'info'|null;reminder_activity:Activity[];reminder_delivery_health:DeliveryHealth;total_pending_requests:number;task_admission_halted:boolean;recovery:boolean;reminders_connected:boolean;ai_planning_connected:false};
function record(value:unknown):value is Record<string,unknown>{return typeof value==='object'&&value!==null&&!Array.isArray(value)}
function parse(value:unknown):View{
 if(!record(value)||value.schema!==1||!Array.isArray(value.items)||value.items.length>8
  ||!Number.isInteger(value.total_pending_requests)||Number(value.total_pending_requests)<0
  ||typeof value.task_admission_halted!=='boolean'||typeof value.recovery!=='boolean'
  ||![null,'critical','warning','info'].includes(value.highest_level as null|string)
  ||typeof value.reminders_connected!=='boolean'||value.ai_planning_connected!==false||value.execution_started!==false
  ||!Array.isArray(value.reminder_activity)||value.reminder_activity.length>5
  ||!record(value.reminder_delivery_health)
  ||!['never','pending','confirmed','uncertain','suppressed'].includes(String(value.reminder_delivery_health.state))
  ||typeof value.reminder_delivery_health.action_required!=='boolean'
  ||!(value.reminder_delivery_health.last_slot===null||(typeof value.reminder_delivery_health.last_slot==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value.reminder_delivery_health.last_slot))))throw new Error();
 const seen=new Set<string>();
 const items=value.items.map(raw=>{
  if(!record(raw)||typeof raw.code!=='string'||!/^[A-Z_]{3,40}$/.test(raw.code)||seen.has(raw.code)
   ||!['critical','warning','info'].includes(String(raw.level))||!Number.isInteger(raw.count)||Number(raw.count)<1
   ||typeof raw.label!=='string'||!raw.label||raw.label.length>100
   ||!['immediate','soon','normal'].includes(String(raw.urgency))||raw.confidence!=='authoritative'
   ||!['execution','planning'].includes(String(raw.impact))
   ||!['control-center','task-results','projects-heading'].includes(String(raw.target)))throw new Error();
  seen.add(raw.code);return {code:raw.code,level:raw.level as Item['level'],count:Number(raw.count),label:raw.label,
   urgency:String(raw.urgency),confidence:String(raw.confidence),impact:String(raw.impact),target:raw.target as Item['target']};
 });
 const reminder_activity=value.reminder_activity.map(raw=>{if(!record(raw)||!Number.isInteger(raw.sequence)||Number(raw.sequence)<1
  ||typeof raw.slot!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(raw.slot)
  ||!['queued','suppressed','critical'].includes(String(raw.outcome))
  ||!(raw.delivery_state===null||['NEW','SENDING','SENT','UNCERTAIN','CANCELLED'].includes(String(raw.delivery_state)))
  ||!Number.isInteger(raw.schedule_version)||Number(raw.schedule_version)<1||typeof raw.critical_quiet_bypass!=='boolean')throw new Error();
  return raw as unknown as Activity});
 return {items,highest_level:value.highest_level as View['highest_level'],reminder_activity,reminder_delivery_health:value.reminder_delivery_health as unknown as DeliveryHealth,total_pending_requests:Number(value.total_pending_requests),task_admission_halted:value.task_admission_halted,
  recovery:value.recovery,reminders_connected:value.reminders_connected,ai_planning_connected:false};
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
  {view&&<>{view.highest_level&&<p><strong>Высший приоритет:</strong> {view.highest_level==='critical'?'критический':view.highest_level==='warning'?'требует внимания':'информационный'}.</p>}
   {view.items.length?<ul>{view.items.map(item=><li key={item.code} data-level={item.level}><strong>{item.count}</strong> · {item.label} · <a href={'#'+item.target}>Открыть раздел</a></li>)}</ul>:<p>Пунктов, требующих внимания, сейчас нет.</p>}
   {view.reminder_activity.length>0&&<><h3>Последние сводки</h3><ul>{view.reminder_activity.map(item=><li key={item.sequence}>
    {item.slot}: {item.delivery_state==='UNCERTAIN'?'доставка не подтверждена':item.outcome==='suppressed'?'без повтора — состояние не изменилось':item.outcome==='critical'?'критическое изменение поставлено в доставку':'поставлена в доставку'}
    {item.critical_quiet_bypass?' · критическое уведомление в тихие часы':''}</li>)}</ul></>}
   {view.reminder_delivery_health.action_required&&<p role="alert">Доставка последнего Telegram-напоминания не подтверждена и требует проверки. <a href="#reminders-heading">Открыть напоминания</a></p>}
   <p>{view.reminders_connected?'Telegram-напоминания включены по сохранённому расписанию.':'Telegram-напоминания выключены.'} AI-планирование запросов ещё не подключено.</p>
   <button disabled={loading} onClick={()=>void reload()}>Обновить сводку</button></>}
 </section>;
}
