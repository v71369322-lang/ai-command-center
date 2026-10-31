import React, {useCallback, useEffect, useRef, useState} from 'react';

type Request=(path:string,body?:unknown,signal?:AbortSignal)=>Promise<unknown>;
type Schedule={version:number;configured:boolean;enabled:boolean;timezone?:string;report_times?:string[];quiet_start?:string;quiet_end?:string};
function record(value:unknown):value is Record<string,unknown>{return typeof value==='object'&&value!==null&&!Array.isArray(value)}
function parse(value:unknown):Schedule{
 if(!record(value)||!Number.isInteger(value.version)||Number(value.version)<0||typeof value.configured!=='boolean'||typeof value.enabled!=='boolean')throw new Error();
 if(!value.configured){if(value.version!==0||value.enabled!==false)return {version:0,configured:false,enabled:false};return {version:0,configured:false,enabled:false}}
 if(typeof value.timezone!=='string'||!Array.isArray(value.report_times)||value.report_times.some(v=>typeof v!=='string')
  ||typeof value.quiet_start!=='string'||typeof value.quiet_end!=='string')throw new Error();
 return {version:Number(value.version),configured:true,enabled:value.enabled,timezone:value.timezone,
  report_times:value.report_times as string[],quiet_start:value.quiet_start,quiet_end:value.quiet_end};
}

export function ReminderSettings({request}:{request:Request}){
 const [value,setValue]=useState<Schedule|null>(null),[timezone,setTimezone]=useState(''),[times,setTimes]=useState('08:00, 14:00, 21:00');
 const [quietStart,setQuietStart]=useState('23:00'),[quietEnd,setQuietEnd]=useState('08:00');
 const [enabled,setEnabled]=useState(false),[busy,setBusy]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const generation=useRef(0);
 const reload=useCallback(async()=>{const current=++generation.current;setBusy(true);setError('');try{const next=parse(await request('attention/schedule'));
  if(current===generation.current){setValue(next);setEnabled(next.enabled);if(next.configured){setTimezone(next.timezone??'');setTimes((next.report_times??[]).join(', '));setQuietStart(next.quiet_start??'23:00');setQuietEnd(next.quiet_end??'08:00')}}}
  catch{if(current===generation.current)setError('Настройки напоминаний недоступны.')}finally{if(current===generation.current)setBusy(false)}},[request]);
 useEffect(()=>{void reload()},[reload]);
 async function save(){if(!value||busy)return;setBusy(true);setError('');setNotice('');const report_times=times.split(',').map(v=>v.trim()).filter(Boolean);
  try{const next=parse(await request('attention/schedule',{enabled,timezone,report_times,quiet_start:quietStart,quiet_end:quietEnd,
   expected_version:value.version,operation_id:crypto.randomUUID()}));setValue(next);setNotice('Расписание сохранено. Оно не запускает AI или задачи.');}
  catch{setError('Расписание не сохранено. Проверьте часовой пояс и время, затем обновите настройки.')}finally{setBusy(false)}}
 return <section aria-labelledby="reminders-heading"><h2 id="reminders-heading">Напоминания</h2>
  <p>До сохранения расписание выключено. Отчёты используют только сводку Центра внимания.</p>
  {busy&&!value&&<p role="status">Загружаем настройки…</p>}{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
  {value&&<><label>Часовой пояс IANA<input value={timezone} placeholder="Asia/Almaty" disabled={busy} onChange={e=>setTimezone(e.target.value)}/></label>
   <label>Время отчётов через запятую<input value={times} disabled={busy} onChange={e=>setTimes(e.target.value)}/></label>
   <label>Тихие часы с<input type="time" value={quietStart} disabled={busy} onChange={e=>setQuietStart(e.target.value)}/></label>
   <label>Тихие часы до<input type="time" value={quietEnd} disabled={busy} onChange={e=>setQuietEnd(e.target.value)}/></label>
   <label><input type="checkbox" checked={enabled} disabled={busy} onChange={e=>setEnabled(e.target.checked)}/> Включить Telegram-отчёты</label>
   <button disabled={busy} onClick={()=>void save()}>Сохранить расписание</button><button disabled={busy} onClick={()=>void reload()}>Обновить</button></>}
 </section>;
}
