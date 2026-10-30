import React, {useEffect, useState} from 'react';
import {ProjectSetup} from './ProjectSetup';

type Request=(path:string,body?:unknown,signal?:AbortSignal)=>Promise<unknown>;
const components=[
 ['repository','Репозиторий','Проверить доступ к нужному репозиторию и согласовать разрешённые операции.'],
 ['verification_environment','Среда проверки','Подготовить изолированную сборку и тесты без рабочих данных.'],
 ['deployment_channel','Доставка на сервер','Настроить установку разрешённой версии и проверку после обновления.'],
] as const;
function record(value:unknown):value is Record<string,unknown>{return typeof value==='object'&&value!==null&&!Array.isArray(value)}
function parse(value:unknown,projectId:string):string{
 if(!record(value)||value.schema!==1||value.scope!=='PLAN_ONLY'||value.project_id!==projectId
   ||value.checked_at!==null||value.execution_connected!==false||value.external_checks_performed!==false
   ||!Array.isArray(value.actions_enabled)||value.actions_enabled.length!==0
   ||typeof value.expected_repository!=='string'||value.expected_repository.length>150
   ||!/^v71369322-lang\/[A-Za-z0-9_-]+$/.test(value.expected_repository)
   ||!Array.isArray(value.components)||value.components.length!==components.length)throw new Error();
 const rows=value.components;
 if(!components.every(([id],i)=>record(rows[i])&&rows[i].id===id&&rows[i].state==='NOT_CHECKED'))throw new Error();
 return value.expected_repository;
}

export function ProjectConnection({projectId,label,request,onSaved}:{projectId:string;label:string;request:Request;onSaved:()=>Promise<void>}){
 const [open,setOpen]=useState(false),[attempt,setAttempt]=useState(0);
 const [repository,setRepository]=useState<string|null>(null),[error,setError]=useState(false);
 useEffect(()=>{
  setRepository(null);setError(false);
  if(!open)return;
  const controller=new AbortController();let current=true;
  const timer=window.setTimeout(()=>controller.abort(),10000);
  void (async()=>{
   try{
    const value=parse(await request('projects/'+projectId+'/connection-plan',undefined,controller.signal),projectId);
    if(current)setRepository(value);
   }catch{if(current)setError(true)}
   finally{window.clearTimeout(timer)}
  })();
  return()=>{current=false;controller.abort();window.clearTimeout(timer)};
 },[open,attempt,projectId,request]);
 return <details className="project-connection" onToggle={event=>setOpen(event.currentTarget.open)}>
  <summary>Подключение: {label}</summary>
  {open&&<div role="region" aria-label={'План подключения: '+label}>
   {error?<><p role="alert">План подключения недоступен. Очередь запросов работает отдельно.</p>
    <button onClick={()=>setAttempt(value=>value+1)}>Повторить загрузку плана</button></>
   :repository?<>
    <p>Ожидаемый репозиторий: <span>{repository}</span>.</p>
    <p>Это план подключения. Доступ к репозиторию, среда проверки и доставка на сервер здесь ещё не проверялись.</p>
    <ol>{components.map(([id,title,description])=><li key={id}><strong>{title}: не проверено.</strong> {description}</li>)}</ol>
    <p>После подключения: задача → проверка изменений → PR → разрешённое обновление → отчёт.</p>
    <p>Просмотр плана не подключает проект, не запускает задачи и не разрешает расходы.</p>
    <ProjectSetup projectId={projectId} label={label} repository={repository} request={request} onSaved={onSaved}/>
   </>:<p role="status">Загружаем план подключения…</p>}
  </div>}
 </details>
}
