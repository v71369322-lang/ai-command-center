import React, {useCallback, useEffect, useRef, useState} from 'react';
import {ProjectConnection} from './ProjectConnection';
import {ProjectSetupOverview} from './ProjectSetup';
import {RequestReview} from './RequestReview';

type Request=(path:string,body?:unknown,signal?:AbortSignal)=>Promise<unknown>;
const ids=['command-center','vanilla-sugar','lnauto','capital-lab'] as const;
type Project=typeof ids[number];
type Filter=Project|'all'|'unassigned';
type Row={id:string;text:string;project_id:Project|null;assignment_version:number};
type View={projects:{id:Project;label:string}[];requests:Row[];counts:Record<string,number>;total_pending:number;filter:Filter};
function record(value:unknown):value is Record<string,unknown>{return typeof value==='object'&&value!==null&&!Array.isArray(value)}
function project(value:unknown):value is Project{return typeof value==='string'&&ids.includes(value as Project)}
function parse(value:unknown,filter:Filter):View{
 if(!record(value)||value.ai_planning_connected!==false||value.filter!==filter||!Array.isArray(value.projects)
   ||value.projects.length!==4||!Array.isArray(value.requests)||value.requests.length>50||!record(value.counts)
   ||!Number.isInteger(value.total_pending)||Number(value.total_pending)<0||Number(value.total_pending)>1000)throw new Error();
 const projects=value.projects.map((item:unknown,index)=>{
  if(!record(item)||item.id!==ids[index]||typeof item.label!=='string'||!item.label||item.label.length>64
    ||item.execution_connected!==false)throw new Error();
  return {id:item.id as Project,label:item.label};
 });
 const counts=value.counts;
 if(Object.keys(counts).length!==5||!['unassigned',...ids].every(key=>Number.isInteger(counts[key])&&Number(counts[key])>=0)
   ||Object.values(counts).reduce((sum:number,n)=>sum+Number(n),0)!==value.total_pending)throw new Error();
 const seen=new Set<string>();
 const rows=value.requests.map((item:unknown)=>{
  if(!record(item)||typeof item.id!=='string'||!/^([a-f0-9]{64}):[0-9]{1,16}$/.test(item.id)||seen.has(item.id)
    ||item.state!=='NEEDS_PLANNING'||typeof item.text!=='string'||!item.text||item.text.length>2000
    ||item.project_id!==null&&!project(item.project_id)||!Number.isInteger(item.assignment_version)
    ||Number(item.assignment_version)<0||Number(item.assignment_version)>1000
    ||filter!=='all'&&(item.project_id??'unassigned')!==filter)throw new Error();
  seen.add(item.id);
  return {id:item.id,text:item.text,project_id:item.project_id as Project|null,assignment_version:Number(item.assignment_version)};
 });
 return {projects,requests:rows,counts:counts as Record<string,number>,total_pending:Number(value.total_pending),filter};
}

function SavedRow({row,projects,disabled,save,request,onSaved}:{row:Row;projects:View['projects'];disabled:boolean;save:(row:Row,project:Project|null)=>void;request:Request;onSaved:()=>Promise<void>}){
 const [chosen,setChosen]=useState<Project|null>(row.project_id);
 const number=row.id.split(':')[1];
 return <li className="project-request">
  <h3>Запрос №{number}</h3>
  <details><summary>Текст запроса</summary><p className="telegram-request-text">{row.text}</p></details>
  <p>Ожидает планирования. Выполнение не запускалось.</p>
  <label htmlFor={'project-'+row.id}>Проект запроса №{number}</label><select id={'project-'+row.id} value={chosen??''} disabled={disabled}
   onChange={event=>setChosen(event.target.value===''?null:event.target.value as Project)}>
   <option value="">Не распределён</option>{projects.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}
  </select>
  <button disabled={disabled||chosen===row.project_id} onClick={()=>save(row,chosen)}>Сохранить проект</button>
  <RequestReview row={row} request={request} onSaved={onSaved}/>
 </li>
}

export function ProjectInbox({request,onSaved}:{request:Request;onSaved:()=>Promise<void>}){
 const [setupRevision,setSetupRevision]=useState(0);
 const [filter,setFilter]=useState<Filter>('all');
 const [view,setView]=useState<View|null>(null);
 const [loading,setLoading]=useState(true),[saving,setSaving]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const generation=useRef(0),active=useRef<AbortController|null>(null);
 const reload=useCallback(async()=>{
  const current=++generation.current;
  active.current?.abort();const controller=new AbortController();active.current=controller;
  setLoading(true);setError('');setView(null);
  const timer=window.setTimeout(()=>controller.abort(),10000);
  try{
   const next=parse(await request('project-inbox?project='+filter,undefined,controller.signal),filter);
   if(current===generation.current)setView(next);
  }catch{if(current===generation.current)setError('Очередь проектов недоступна. Обновите список. Остальные разделы работают отдельно.')}
  finally{window.clearTimeout(timer);controller.abort();if(current===generation.current){setLoading(false);setSaving(false)}}
 },[request,filter]);
 useEffect(()=>{setNotice('');void reload();return()=>{++generation.current;active.current?.abort()}},[reload]);
 async function save(row:Row,chosen:Project|null){
  if(saving||loading||error)return;
  const current=generation.current,controller=new AbortController();active.current=controller;
  const operation=crypto.randomUUID();
  const timer=window.setTimeout(()=>controller.abort(),10000);
  setSaving(true);setNotice('');
  try{
   const value=await request('project-inbox/assign',{request_id:row.id,project_id:chosen,
    expected_version:row.assignment_version,operation_id:operation},controller.signal);
   if(!record(value)||value.request_id!==row.id||value.project_id!==chosen||value.version!==row.assignment_version+1
     ||value.operation_id!==operation||value.execution_started!==false)throw new Error();
   if(current===generation.current){
    await onSaved();
    if(current===generation.current){await reload();if(generation.current===current+1)setNotice('Проект сохранён. Выполнение не запускалось.')}
   }
  }catch{if(current===generation.current)setError('Сохранение не подтверждено. Обновите список перед следующей попыткой.')}
  finally{window.clearTimeout(timer);controller.abort();if(current===generation.current)setSaving(false)}
 }
 return <section className="project-inbox" aria-labelledby="projects-heading" aria-busy={loading||saving}>
  <h2 id="projects-heading">Проекты и запросы</h2>
  <p>Выбор проекта упорядочивает запросы. Он не разрешает запуск AI или доступ к CRM.</p>
  {view&&<ProjectSetupOverview request={request} revision={setupRevision}/>}
  {view&&<ul>{view.projects.map(item=><li key={item.id}>{item.label}: {view.counts[item.id]} · AI-разработка не подключена
   <ProjectConnection projectId={item.id} label={item.label} request={request} onSaved={async()=>{
    await onSaved();setSetupRevision(v=>v+1);
   }}/></li>)}</ul>}
  <label htmlFor="project-filter">Показать запросы</label><select id="project-filter" value={filter} disabled={loading||saving} onChange={event=>setFilter(event.target.value as Filter)}>
   <option value="all">Все проекты</option><option value="unassigned">Не распределены</option>
   {(view?.projects??ids.map(id=>({id,label:id}))).map(item=><option key={item.id} value={item.id}>{item.label}</option>)}
  </select>
  {loading&&<p role="status">Загружаем очередь проектов…</p>}
  {notice&&<p role="status">{notice}</p>}
  {error&&<p role="alert">{error}</p>}
  {view&&<><p>Ожидают планирования: {view.total_pending}. Не распределены: {view.counts.unassigned}.</p>
   {view.requests.length===0?<p>В этом разделе запросов пока нет.</p>:<ul className="project-requests">
    {view.requests.map(row=><SavedRow key={row.id+':'+row.assignment_version} row={row} projects={view.projects}
     disabled={loading||saving||Boolean(error)} request={request} onSaved={onSaved} save={(item,chosen)=>void save(item,chosen)}/>)}</ul>}
   {view.requests.length===50&&<p>Показаны последние 50 запросов выбранного раздела.</p>}</>}
  <button disabled={loading||saving} onClick={()=>{setNotice('');void reload()}}>Обновить очередь проектов</button>
 </section>
}
