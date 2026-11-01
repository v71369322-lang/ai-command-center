import React,{useEffect,useRef,useState} from 'react';
import {RequestReview} from './RequestReview';

type Request=(path:string,body?:unknown,signal?:AbortSignal)=>Promise<unknown>;
const projects:Record<string,string>={all:'Все проекты',unassigned:'Не распределены','command-center':'AI Commander',
 'vanilla-sugar':'Ваниль и Сахар',lnauto:'LNAuto','capital-lab':'Capital Lab'};
const stages:Record<string,string>={all:'Все стадии',select_project:'Выбрать проект',complete_setup:'Заполнить настройки',
 prepare_plan:'Составить план',refresh_plan:'Обновить устаревший план',answer_questions:'Уточнить вопросы',verify_scope:'Сверить задачу и подключения'};
type Row={id:string;text:string;project_id:string|null;assignment_version:number;setup_version:number|null;
 plan_version:number;plan_state:string;setup_state:string;origin:string|null;stage:string};
type View={requests:Row[];total:number;matching:number;pages:number;counts:Record<string,number>;snapshot:string;observed:string};
function record(v:unknown):v is Record<string,unknown>{return typeof v==='object'&&v!==null&&!Array.isArray(v)}
function integer(v:unknown,max:number):v is number{return typeof v==='number'&&Number.isInteger(v)&&v>=0&&v<=max}
function parse(value:unknown,project:string,stage:string,page:number,snapshot:string|null):View{
 if(!record(value)||value.schema!==1||value.scope!=='PREPARATION_QUEUE_ONLY'||value.project!==project||value.stage!==stage
  ||value.page!==page||value.page_size!==10||!integer(value.pages,100)||value.pages<1||page>value.pages
  ||!integer(value.total_pending,1000)||!integer(value.total_matching,1000)||value.total_matching>value.total_pending
  ||value.pages!==Math.max(1,Math.ceil(value.total_matching/10))||!Array.isArray(value.requests)||!record(value.stage_counts)||!record(value.project_counts)
  ||typeof value.snapshot_digest!=='string'||!/^[a-f0-9]{64}$/.test(value.snapshot_digest)||snapshot!==null&&snapshot!==value.snapshot_digest
  ||typeof value.observed_at!=='string'||value.observed_at.length>64||!Number.isFinite(Date.parse(value.observed_at))
  ||!['execution_ready','execution_authorized','external_checks_performed','provider_called','task_created'].every(k=>value[k]===false)
  ||!Array.isArray(value.actions_enabled)||value.actions_enabled.length!==0)throw new Error();
 const pc=value.project_counts,sc=value.stage_counts;
 const pkeys=Object.keys(projects).filter(k=>k!=='all'),skeys=Object.keys(stages).filter(k=>k!=='all');
 if(Object.keys(pc).length!==5||!pkeys.every(k=>integer(pc[k],1000))||Object.values(pc).reduce<number>((a,b)=>a+Number(b),0)!==value.total_pending
  ||Object.keys(sc).length!==6||!skeys.every(k=>integer(sc[k],1000))
  ||Object.values(sc).reduce<number>((a,b)=>a+Number(b),0)!==(project==='all'?value.total_pending:pc[project])
  ||(stage==='all'?Object.values(sc).reduce<number>((a,b)=>a+Number(b),0):sc[stage])!==value.total_matching
  ||value.requests.length!==Math.min(10,Math.max(0,value.total_matching-(page-1)*10)))throw new Error();
 const seen=new Set<string>();
 const rows=value.requests.map(v=>{
  if(!record(v)||typeof v.id!=='string'||!/^([a-f0-9]{64}):(0|[1-9][0-9]{0,15})$/.test(v.id)||Number(v.id.split(':')[1])>=2**53||seen.has(v.id)
   ||typeof v.text!=='string'||!v.text||v.text.length>2000||v.project_id!==null&&(typeof v.project_id!=='string'||!pkeys.includes(v.project_id)||v.project_id==='unassigned')
   ||!integer(v.assignment_version,1000)||!integer(v.plan_version,100)||typeof v.stage!=='string'||!skeys.includes(v.stage)
   ||project!=='all'&&(v.project_id??'unassigned')!==project||stage!=='all'&&v.stage!==stage
   ||v.project_id!==null&&(!integer(v.setup_version,500)||v.assignment_version<1)||v.project_id===null&&v.setup_version!==null
   ||typeof v.plan_state!=='string'||!['MISSING','STALE','CURRENT','NEEDS_CLARIFICATION'].includes(v.plan_state)
   ||(v.plan_state==='MISSING'?(v.plan_version!==0||v.origin!==null):(v.plan_version<1||!['owner_authored','owner_supplied_unverified'].includes(String(v.origin)))))throw new Error();
  if(typeof v.setup_state!=='string'||!['UNASSIGNED','EMPTY','INCOMPLETE','COMPLETE'].includes(v.setup_state)
   ||(v.project_id===null)!==(v.setup_state==='UNASSIGNED')||v.project_id!==null&&(v.setup_version===0)!==(v.setup_state==='EMPTY'))throw new Error();
  const step=v.project_id===null?'select_project':v.setup_state!=='COMPLETE'?'complete_setup':v.plan_state==='MISSING'?'prepare_plan'
   :v.plan_state==='STALE'?'refresh_plan':v.plan_state==='NEEDS_CLARIFICATION'?'answer_questions':'verify_scope';
  if(step!==v.stage)throw new Error();
  seen.add(v.id);return v as Row;
 });
 return {requests:rows,total:value.total_pending,matching:value.total_matching,pages:value.pages,counts:sc as Record<string,number>,
  snapshot:value.snapshot_digest,observed:value.observed_at};
}

export function PreparationQueue({request,onSaved,revision}:{request:Request;onSaved:()=>Promise<void>;revision:number}){
 const [open,setOpen]=useState(false),[project,setProject]=useState('all'),[stage,setStage]=useState('all');
 const [cursor,setCursor]=useState<{page:number;snapshot:string|null}>({page:1,snapshot:null});
 const [attempt,setAttempt]=useState(0),[view,setView]=useState<View|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(false);
 const generation=useRef(0);
 useEffect(()=>{setCursor({page:1,snapshot:null})},[revision]);
 useEffect(()=>{
  const current=++generation.current;setView(null);setError(false);setBusy(false);if(!open)return;
  const controller=new AbortController(),timer=window.setTimeout(()=>controller.abort(),10000);setBusy(true);
  const query=new URLSearchParams({project,stage,page:String(cursor.page)});if(cursor.snapshot)query.set('snapshot',cursor.snapshot);
  void(async()=>{try{
   const next=parse(await request('project-inbox/preparation?'+query,undefined,controller.signal),project,stage,cursor.page,cursor.snapshot);
   if(current===generation.current)setView(next);
  }catch{if(current===generation.current)setError(true)}finally{window.clearTimeout(timer);controller.abort();if(current===generation.current)setBusy(false)}})();
  return()=>{++generation.current;controller.abort();window.clearTimeout(timer)};
 },[open,project,stage,cursor,attempt,request]);
 function restart(){setCursor({page:1,snapshot:null});setAttempt(v=>v+1)}
 return <details className="preparation-queue" onToggle={e=>setOpen(e.currentTarget.open)}>
  <summary>Стадии подготовки запросов</summary>
  {open&&<section aria-label="Стадии подготовки запросов" aria-busy={busy}>
   <p>Здесь видно, какой следующий шаг нужен каждому запросу. Стадия подготовки не разрешает запуск задачи или расходы.</p>
   <label htmlFor="preparation-project">Проект в обзоре подготовки</label><select id="preparation-project" value={project}
    onChange={e=>{setProject(e.target.value);setCursor({page:1,snapshot:null})}}>{Object.entries(projects).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select>
   <label htmlFor="preparation-stage">Стадия подготовки</label><select id="preparation-stage" value={stage}
    onChange={e=>{setStage(e.target.value);setCursor({page:1,snapshot:null})}}>{Object.entries(stages).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select>
   {busy&&<p role="status">Читаем стадии подготовки…</p>}
   {error&&<p role="alert">Обзор недоступен или очередь изменилась. Обновите обзор с первой страницы.</p>}
   {view&&<><p>Найдено: {view.matching} из {view.total}. Страница {cursor.page}/{view.pages}.</p><p>Снимок UTC: {view.observed}</p>
    <ul aria-label="Количество запросов по стадиям">{Object.entries(view.counts).map(([k,v])=><li key={k}>{stages[k]}: {v}</li>)}</ul>
    {view.requests.length===0?<p>На этой стадии запросов пока нет.</p>:<ul className="project-requests">{view.requests.map(row=><li key={row.id} className="project-request">
     <h3>Запрос №{row.id.split(':')[1]}</h3><p>{projects[row.project_id??'unassigned']}. Следующий шаг: {stages[row.stage]}.</p>
     <details><summary>Текст запроса</summary><p className="telegram-request-text">{row.text}</p></details>
     <p>Версия настроек: {row.setup_version??'проект не выбран'}. Версия плана: {row.plan_version}.</p>
     <RequestReview row={row} request={request} onSaved={onSaved}/>
    </li>)}</ul>}
    <div className="preparation-pages"><button disabled={busy||cursor.page===1} onClick={()=>setCursor({page:cursor.page-1,snapshot:view.snapshot})}>Предыдущая страница подготовки</button>
     <button disabled={busy||cursor.page===view.pages} onClick={()=>setCursor({page:cursor.page+1,snapshot:view.snapshot})}>Следующая страница подготовки</button></div>
   </>}
   <button disabled={busy} onClick={restart}>Обновить стадии подготовки</button>
  </section>}
 </details>
}
