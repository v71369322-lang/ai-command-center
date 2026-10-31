import React,{useEffect,useRef,useState} from 'react';

type Request=(path:string,body?:unknown,signal?:AbortSignal)=>Promise<unknown>;
export type PlanDraft={summary:string;steps:{description:string;acceptance:string[]}[];questions:string[]};
export type PlanReference={request_id:string;expected_context_digest:string;expected_assignment_version:number;
 expected_setup_version:number;expected_setup_digest:string;expected_plan_version:number};
type Form={summary:string;steps:{description:string;criteria:string}[];questions:string};
function record(v:unknown):v is Record<string,unknown>{return typeof v==='object'&&v!==null&&!Array.isArray(v)}
function same(a:unknown,b:unknown){return JSON.stringify(a)===JSON.stringify(b)}
function lines(value:string){return value.split('\n').map(v=>v.trim()).filter(Boolean)}

export function ManualPlanEditor({reference,initial,request,onSaved,onReload}:{reference:PlanReference;initial:PlanDraft|null;
 request:Request;onSaved:()=>Promise<void>;onReload:()=>void}){
 const [form,setForm]=useState<Form>(()=>({summary:initial?.summary??'',questions:initial?.questions.join('\n')??'',
  steps:initial?.steps.map(v=>({description:v.description,criteria:v.acceptance.join('\n')}))??[{description:'',criteria:''}]}));
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[previewError,setPreviewError]=useState('');
 const [preview,setPreview]=useState<PlanDraft|null>(null);
 const generation=useRef(0),active=useRef<AbortController|null>(null);
 useEffect(()=>()=>{++generation.current;active.current?.abort()},[]);
 function change(value:Partial<Form>){setForm(old=>({...old,...value}));setPreview(null);setPreviewError('')}
 function step(index:number,value:Partial<Form['steps'][number]>){change({steps:form.steps.map((v,i)=>i===index?{...v,...value}:v)})}
 async function action(kind:'preview'|'save'){
  if(busy||error)return;
  const current=generation.current,controller=new AbortController();active.current=controller;
  const timer=window.setTimeout(()=>controller.abort(),10000);
  const draft:PlanDraft={summary:form.summary.trim(),steps:form.steps.map(v=>({description:v.description.trim(),acceptance:lines(v.criteria)})),questions:lines(form.questions)};
  const body={...reference,draft},operation=crypto.randomUUID();
  setBusy(true);setPreviewError('');
  try{
   if(kind==='preview'){
    setPreview(null);
    const value=await request('project-inbox/plan/preview',body,controller.signal);
    if(!record(value)||value.scope!=='MANUAL_PLAN_DRAFT_ONLY'||value.request_id!==reference.request_id||value.stored!==false
     ||value.provider_called!==false||value.execution_authorized!==false||value.task_created!==false
     ||typeof value.preview_digest!=='string'||!/^[a-f0-9]{64}$/.test(value.preview_digest)||!record(value.proposal))throw new Error();
    const p=value.proposal;
    if(p.context_digest!==reference.expected_context_digest||p.disposition!==(draft.questions.length?'needs_clarification':'ready_for_review')
     ||p.summary!==draft.summary||!same(p.steps,draft.steps)||!same(p.questions,draft.questions))throw new Error();
    if(current===generation.current)setPreview(draft);
   }else{
    if(!preview||!same(preview,draft))throw new Error();
    const value=await request('project-inbox/plan',{...body,operation_id:operation},controller.signal);
    if(!record(value)||value.scope!=='MANUAL_PLAN_DRAFT_ONLY'||value.request_id!==reference.request_id||value.operation_id!==operation
     ||value.version!==reference.expected_plan_version+1||value.context_digest!==reference.expected_context_digest
     ||value.origin!=='owner_authored'||value.stored!==true||value.provider_called!==false||value.provider_evidence_verified!==false
     ||value.execution_authorized!==false||value.task_created!==false)throw new Error();
    if(current===generation.current){await onSaved();if(current===generation.current)onReload()}
   }
  }catch{if(current===generation.current){
   if(kind==='preview')setPreviewError('Предпросмотр не подтверждён. Проверьте поля; если сведения изменились, загрузите текущий план.');
   else setError('Сохранение не подтверждено. Загрузите текущий план перед следующей записью.');
  }}finally{window.clearTimeout(timer);controller.abort();if(current===generation.current)setBusy(false)}
 }
 async function reconcile(){
  if(busy)return;const current=generation.current;setBusy(true);
  try{await onSaved();if(current===generation.current)onReload()}
  catch{if(current===generation.current)setError('Текущие сведения недоступны. Обновите очередь перед следующей записью.')}
  finally{if(current===generation.current)setBusy(false)}
 }
 const prefix='manual-'+reference.request_id+'-';
 return <section className="manual-plan" aria-label="Редактор ручного плана" aria-busy={busy}>
  <h4>Ручной план</h4><p>Автором будете вы. Черновик сохраняется без AI-вызова, запуска задачи и разрешения расходов. Ключи, пароли и клиентские данные не вводите.</p>
  {busy&&<p role="status">Обрабатываем ручной план…</p>}{(error||previewError)&&<p role="alert">{error||previewError}</p>}
  <fieldset disabled={busy||Boolean(error)}>
   <label htmlFor={prefix+'summary'}>Цель ручного плана</label>
   <input id={prefix+'summary'} value={form.summary} maxLength={300} onChange={e=>change({summary:e.target.value})}/>
   {form.steps.map((v,i)=><fieldset key={i}><legend>Шаг {i+1}</legend>
    <label htmlFor={prefix+'step-'+i}>Описание шага {i+1}</label>
    <input id={prefix+'step-'+i} value={v.description} maxLength={300} onChange={e=>step(i,{description:e.target.value})}/>
    <label htmlFor={prefix+'criteria-'+i}>Критерии шага {i+1} (до 3 строк)</label>
    <textarea id={prefix+'criteria-'+i} value={v.criteria} maxLength={902} onChange={e=>step(i,{criteria:e.target.value})}/>
    <button disabled={form.steps.length===1} onClick={()=>change({steps:form.steps.filter((_,index)=>index!==i)})}>Убрать шаг {i+1}</button>
   </fieldset>)}
   <button disabled={form.steps.length>=8} onClick={()=>change({steps:[...form.steps,{description:'',criteria:''}]})}>Добавить шаг</button>
   <label htmlFor={prefix+'questions'}>Вопросы к плану (до 5 строк)</label>
   <textarea id={prefix+'questions'} value={form.questions} maxLength={1504} onChange={e=>change({questions:e.target.value})}/>
   <button onClick={()=>void action('preview')}>Предпросмотр ручного плана</button>
   <button disabled={!preview} onClick={()=>void action('save')}>Сохранить ручной план</button>
  </fieldset>
  {preview&&<div role="region" aria-label="Предпросмотр ручного плана"><p>Будет сохранена версия {reference.expected_plan_version+1}: {preview.summary}.</p>
   <ol>{preview.steps.map((v,i)=><li key={i}>{v.description}<ul>{v.acceptance.map((s,j)=><li key={j}>{s}</li>)}</ul></li>)}</ol>
   <p>Вопросов: {preview.questions.length}. Настройки проекта: версия {reference.expected_setup_version}. Это черновик владельца, не разрешение на выполнение.</p></div>}
  <button disabled={busy} onClick={()=>void reconcile()}>Загрузить текущий план</button>
 </section>
}
