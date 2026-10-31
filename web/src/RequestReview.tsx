import React, {useEffect, useRef, useState} from 'react';
import {parseDraft,parseReview,names as setupNames} from './ProjectSetup';
import {ManualPlanEditor,type PlanReference} from './ManualPlanEditor';

type Request=(path:string,body?:unknown,signal?:AbortSignal)=>Promise<unknown>;
type Row={id:string;text:string;project_id:string|null;assignment_version:number};
type Proposal={summary:string;steps:{description:string;acceptance:string[]}[];questions:string[]};
const repositories:Record<string,string>={'command-center':'v71369322-lang/ai-command-center','vanilla-sugar':'v71369322-lang/Vanilla-Sugar-CRM',
 lnauto:'v71369322-lang/LNAuto','capital-lab':'v71369322-lang/Capital-Lab'};
const labels:Record<string,string>={assignment:'Выбор проекта',setup:'Настройки проекта',plan:'Предложение плана',
 plan_setup_binding:'Соответствие плана настройкам',repository:'Доступ к репозиторию',verification:'Изолированная проверка',
 delivery:'Доставка на сервер',authorization:'Разрешение задачи и расходов',admission:'Приём новых запусков'};
const next:Record<string,string>={select_project:'Выберите проект для запроса.',complete_setup:'Заполните черновик подключения выбранного проекта выше.',
 prepare_plan:'План запроса ещё не сохранён. Составьте ручной план; AI-планирование обычных запросов пока не подключено.',
 refresh_plan:'Сохранённый план устарел. Требуется новый план для текущих условий.',answer_questions:'Уточните вопросы предложения перед дальнейшей подготовкой.',
 verify_scope:'Сверьте предложение с настройками проекта, затем проверьте доступы и среду выполнения.'};
const states:Record<string,string>={SELECTED:'выбран',UNASSIGNED:'проект не выбран',EMPTY:'черновик пуст',INCOMPLETE:'черновик неполный',
 COMPLETE:'черновик заполнен',MISSING:'не сохранён',STALE:'устарел',CURRENT:'непроверенное предложение',
 NEEDS_CLARIFICATION:'нужны уточнения',NOT_CHECKED:'не проверено',NOT_GRANTED:'не выдано',OPEN:'обычная остановка не включена',
 HALTED:'новые запуски остановлены',RECOVERY:'требуется сверка восстановления'};
states.DECLARED_MATCH='версии черновиков совпадают; внешняя проверка ещё нужна';
type View={project:{label:string;repository:string;version:number;draft:ReturnType<typeof parseDraft>;missing:string[]}|null;
 plan:{state:string;version:number|null;proposal:Proposal|null;origin:string|null};reference:PlanReference|null;
 checks:{id:string;state:string}[];next:string;observed:string};
function record(v:unknown):v is Record<string,unknown>{return typeof v==='object'&&v!==null&&!Array.isArray(v)}
function integer(v:unknown,max:number):v is number{return typeof v==='number'&&Number.isInteger(v)&&v>=0&&v<=max}
function text(v:unknown,max:number):v is string{return typeof v==='string'&&v.length>0&&Array.from(v).length<=max}
function same(a:unknown,b:unknown){return JSON.stringify(a)===JSON.stringify(b)}
function parse(value:unknown,row:Row):View{
 if(!record(value)||value.schema!==1||value.scope!=='REQUEST_REVIEW_ONLY'||value.execution_ready!==false
  ||value.execution_authorized!==false||value.external_checks_performed!==false||value.task_created!==false||value.provider_called!==false
  ||!Array.isArray(value.actions_enabled)||value.actions_enabled.length!==0||!record(value.request)
  ||value.request.id!==row.id||value.request.text!==row.text||value.request.assignment_version!==row.assignment_version
  ||typeof value.source_revision!=='string'||!/^[a-f0-9]{40}$/.test(value.source_revision)
  ||![value.context_digest,value.snapshot_digest,value.request.fingerprint].every(v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v))
  ||typeof value.observed_at!=='string'||value.observed_at.length>64||!Number.isFinite(Date.parse(value.observed_at)))throw new Error();
 let project:View['project']=null,setupState='UNASSIGNED',setupDigest='';
 if(value.project!==null){
  const p=value.project;
  if(!record(p)||p.id!==row.project_id||typeof p.id!=='string'||!(p.id in repositories)||p.repository!==repositories[p.id]
   ||!text(p.label,64)||!integer(p.setup_version,500)||typeof p.setup_digest!=='string'||!/^[a-f0-9]{64}$/.test(p.setup_digest))throw new Error();
  const draft=parseDraft(p.draft),review=parseReview(p.review,draft);
  if(p.setup_version===0&&review.filled!==0)throw new Error();
  setupState=p.setup_version===0?'EMPTY':review.ready_for_operator_review?'COMPLETE':'INCOMPLETE';
  project={label:p.label,repository:p.repository as string,version:p.setup_version,draft,missing:review.missing_fields};
  setupDigest=p.setup_digest;
  if(row.assignment_version<1)throw new Error();
 }else if(row.project_id!==null)throw new Error();
 const p=value.plan;
 if(!record(p)||typeof p.state!=='string'||!['CURRENT','NEEDS_CLARIFICATION','STALE','MISSING'].includes(p.state)
  ||p.provider_evidence_verified!==false||p.setup_binding_verified!==false||!integer(p.latest_version,100))throw new Error();
 let proposal:Proposal|null=null;
 if(p.state==='MISSING'){
  if(p.version!==null||p.latest_version!==0||p.proposal!==null||p.origin!==null||p.setup_reference_state!=='NOT_RECORDED')throw new Error();
 }else{
  if(typeof p.origin!=='string'||!['owner_supplied_unverified','owner_authored'].includes(p.origin)
   ||p.setup_reference_state!==(p.origin==='owner_authored'?(p.state==='STALE'?'STALE':'CURRENT'):'NOT_RECORDED'))throw new Error();
  if(!integer(p.version,100)||p.version<1||p.version!==p.latest_version)throw new Error();
  if(p.state==='STALE'){if(p.proposal!==null)throw new Error()}
  else{
   const d=p.proposal;
   if(!record(d)||d.context_digest!==value.context_digest||!text(d.summary,300)||!Array.isArray(d.questions)||d.questions.length>5
    ||!d.questions.every(v=>text(v,300))||!Array.isArray(d.steps)||d.steps.length<1||d.steps.length>8
    ||d.disposition!==(p.state==='NEEDS_CLARIFICATION'?'needs_clarification':'ready_for_review')
    ||(d.questions.length>0)!==(p.state==='NEEDS_CLARIFICATION'))throw new Error();
   const steps=d.steps.map(v=>{
    if(!record(v)||!text(v.description,300)||!Array.isArray(v.acceptance)||v.acceptance.length<1||v.acceptance.length>3
     ||!v.acceptance.every(s=>text(s,300)))throw new Error();
    return {description:v.description,acceptance:v.acceptance as string[]};
   });
   proposal={summary:d.summary,steps,questions:d.questions as string[]};
  }
 }
 const expected:Record<string,string>={assignment:project?'SELECTED':'UNASSIGNED',setup:setupState,plan:p.state,
  plan_setup_binding:p.setup_reference_state==='CURRENT'?'DECLARED_MATCH':'NOT_CHECKED',repository:'NOT_CHECKED',verification:'NOT_CHECKED',delivery:'NOT_CHECKED',authorization:'NOT_GRANTED'};
 if(!Array.isArray(value.checks)||value.checks.length!==9)throw new Error();
 const checks=value.checks.map((v,i)=>{
  const id=Object.keys(labels)[i];
  if(!record(v)||v.id!==id||typeof v.state!=='string'||(id==='admission'?!['OPEN','HALTED','RECOVERY'].includes(v.state):v.state!==expected[id]))throw new Error();
  return {id,state:v.state};
 });
 const blockers=checks.filter(v=>!['SELECTED','COMPLETE','CURRENT','OPEN','DECLARED_MATCH'].includes(v.state)).map(v=>v.id);
 const key=!project?'select_project':setupState!=='COMPLETE'?'complete_setup':p.state==='MISSING'?'prepare_plan':p.state==='STALE'?'refresh_plan':p.state==='NEEDS_CLARIFICATION'?'answer_questions':'verify_scope';
 if(!same(blockers,value.blocking_checks)||value.next_step!==key)throw new Error();
 const reference=project?{request_id:row.id,expected_context_digest:value.context_digest as string,
  expected_assignment_version:row.assignment_version,expected_setup_version:project.version,expected_setup_digest:setupDigest,
  expected_plan_version:p.latest_version as number}:null;
 return {project,plan:{state:p.state,version:p.version as number|null,proposal,origin:p.origin as string|null},reference,checks,next:key,observed:value.observed_at};
}

export function RequestReview({row,request,onSaved}:{row:Row;request:Request;onSaved:()=>Promise<void>}){
 const [open,setOpen]=useState(false),[attempt,setAttempt]=useState(0),[view,setView]=useState<View|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(false);
 const generation=useRef(0);
 useEffect(()=>{
  const current=++generation.current;setView(null);setError(false);setBusy(false);
  if(!open)return;
  const controller=new AbortController();setBusy(true);const timer=window.setTimeout(()=>controller.abort(),10000);
  void (async()=>{
   try{const data=parse(await request('project-inbox/review?request_id='+encodeURIComponent(row.id),undefined,controller.signal),row);
    if(current===generation.current)setView(data);
   }catch{if(current===generation.current)setError(true)}
   finally{controller.abort();window.clearTimeout(timer);if(current===generation.current)setBusy(false)}
  })();
  return()=>{++generation.current;controller.abort();window.clearTimeout(timer)};
 },[open,attempt,row.id,row.text,row.project_id,row.assignment_version,request]);
 const number=row.id.split(':')[1];
 return <details className="request-review" onToggle={e=>setOpen(e.currentTarget.open)}>
  <summary>Подготовка запроса №{number}</summary>
  {open&&<section aria-label={'Подготовка запроса №'+number} aria-busy={busy}>
   {busy&&<p role="status">Собираем сохранённые сведения…</p>}
   {error&&<p role="alert">Обзор недоступен или сведения изменились. Обновите очередь проектов перед повторным просмотром.</p>}
   {view&&<>
    <p>Сведения на {new Intl.DateTimeFormat('ru-RU',{timeZone:'UTC',dateStyle:'short',timeStyle:'medium'}).format(new Date(view.observed))} UTC. Для новых сведений обновите обзор.</p>
    <h4>Дальнейший шаг</h4><p>{next[view.next]}</p>
    <h4>Готовность запроса</h4><ul>{view.checks.map(v=><li key={v.id}>{labels[v.id]}: {states[v.state]}.</li>)}</ul>
    {view.project&&<><h4>{view.project.label}: настройки версии {view.project.version}</h4>
     <p>Ожидаемый репозиторий: {view.project.repository}.</p>
     <p>Выбранная версия кода: {view.project.draft.repository_revision??'не задана'}. Метка сервера: {view.project.draft.deployment_target??'не задана'}.</p>
     <p>Среда проверки: {({not_selected:'не выбрана',python:'Python',node:'Node.js',python_node:'Python и Node.js'})[view.project.draft.verification_kind]}.</p>
     <p>Способ проверки доставки: {({not_selected:'не выбран',manual_review:'ручная проверка',pipeline_review:'проверка существующего канала'})[view.project.draft.delivery_kind]}.</p>
     {view.project.missing.length>0&&<p>Не заполнено: {view.project.missing.map(k=>setupNames[k]).join(', ')}.</p>}
     <p>Критерии из настроек проекта (текст, не команды):</p><ul>{view.project.draft.acceptance.map((v,i)=><li key={i}>{v}</li>)}</ul>
    </>}
    {view.plan.proposal&&<><h4>Предложение плана, версия {view.plan.version}</h4>
     <p>{view.plan.origin==='owner_authored'?'Автор — владелец. Это ручной черновик, не разрешение на выполнение.':'Источник AI-ответа не подтверждён; предложение ещё не сверено с настройками проекта.'}</p>
     <p>{view.plan.proposal.summary}</p><ol>{view.plan.proposal.steps.map((v,i)=><li key={i}>{v.description}
      <ul>{v.acceptance.map((s,j)=><li key={j}>Критерий: {s}</li>)}</ul></li>)}</ol>
     {view.plan.proposal.questions.length>0&&<><h4>Нужно уточнить</h4><ul>{view.plan.proposal.questions.map((v,i)=><li key={i}>{v}</li>)}</ul></>}
    </>}
    <p>Обзор не проверяет внешние подключения, не создаёт задачу и не выдаёт разрешение на выполнение или расходы.</p>
    {view.reference&&<ManualPlanEditor key={view.reference.expected_context_digest+':'+view.reference.expected_setup_version+':'+view.reference.expected_plan_version}
     reference={view.reference} initial={view.plan.proposal} request={request} onSaved={onSaved} onReload={()=>setAttempt(v=>v+1)}/>}
   </>}
   <button disabled={busy} onClick={()=>setAttempt(v=>v+1)}>Обновить обзор запроса</button>
  </section>}
 </details>
}
