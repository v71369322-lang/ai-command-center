import React, {useCallback, useEffect, useRef, useState} from 'react';

type Request=(path:string,body?:unknown,signal?:AbortSignal)=>Promise<unknown>;
type Draft={repository_revision:string|null;verification_kind:'not_selected'|'python'|'node'|'python_node';
 delivery_kind:'not_selected'|'manual_review'|'pipeline_review';deployment_target:string|null;acceptance:string[]};
type Review={filled:number;missing_fields:string[];ready_for_operator_review:boolean};
type View={version:number;latest_version:number;draft:Draft;draft_digest:string;review:Review;
 history:{version:number;draft_digest:string}[]};
type Form={revision:string;verification:Draft['verification_kind'];delivery:Draft['delivery_kind'];target:string;acceptance:string};
type Preview={draft:Draft;proposed_digest:string;review:Review;changed_fields:string[]};
const fields=['repository_revision','verification_kind','delivery_kind','deployment_target','acceptance'] as const;
const names:Record<string,string>={repository_revision:'Версия кода',verification_kind:'Тип среды проверки',
 delivery_kind:'Способ проверки доставки',deployment_target:'Метка сервера',acceptance:'Критерии результата'};
const checks=['repository_binding','isolated_verification','deployment_binding','separate_task_authorization'];
const ids=['command-center','vanilla-sugar','lnauto','capital-lab'];
const hex=/^[a-f0-9]{64}$/;
function record(x:unknown):x is Record<string,unknown>{return typeof x==='object'&&x!==null&&!Array.isArray(x)}
function integer(x:unknown):x is number{return typeof x==='number'&&Number.isInteger(x)&&x>=0&&x<=500}
function same(a:unknown,b:unknown){return JSON.stringify(a)===JSON.stringify(b)}
function flags(x:Record<string,unknown>){
 if(x.schema!==1||x.scope!=='SETUP_DRAFT_ONLY'||x.execution_connected!==false||x.external_checks_performed!==false
  ||!Array.isArray(x.actions_enabled)||x.actions_enabled.length!==0)throw new Error();
}
function parseDraft(x:unknown):Draft{
 if(!record(x)||Object.keys(x).length!==5||!fields.every(k=>k in x)
  ||x.repository_revision!==null&&(typeof x.repository_revision!=='string'||!/^[a-f0-9]{40}$/.test(x.repository_revision))
  ||typeof x.verification_kind!=='string'||!['not_selected','python','node','python_node'].includes(x.verification_kind)
  ||typeof x.delivery_kind!=='string'||!['not_selected','manual_review','pipeline_review'].includes(x.delivery_kind)
  ||x.deployment_target!==null&&(typeof x.deployment_target!=='string'||!/^[a-z][a-z0-9-]{0,47}$/.test(x.deployment_target))
  ||!Array.isArray(x.acceptance)||x.acceptance.length>8||!x.acceptance.every(v=>typeof v==='string'
    &&v.length>0&&v.length<=200&&v===v.trim()&&!/[\x00-\x1f]/.test(v)&&new TextEncoder().encode(v).length<=400))throw new Error();
 return {repository_revision:x.repository_revision as string|null,verification_kind:x.verification_kind as Draft['verification_kind'],
  delivery_kind:x.delivery_kind as Draft['delivery_kind'],deployment_target:x.deployment_target as string|null,acceptance:x.acceptance as string[]};
}
function parseReview(x:unknown,draft?:Draft):Review{
 if(!record(x)||x.total!==5||!Array.isArray(x.missing_fields)||x.execution_ready!==false||!same(x.blocking_checks,checks))throw new Error();
 const missing=x.missing_fields;
 if(missing.length>5||!fields.filter(k=>missing.includes(k)).every((k,i)=>missing[i]===k)
  ||new Set(missing).size!==missing.length||!missing.every(k=>typeof k==='string'&&fields.includes(k as typeof fields[number]))
  ||x.filled!==5-missing.length||x.ready_for_operator_review!==(missing.length===0))throw new Error();
 if(draft&&!same(missing,fields.filter(k=>draft[k]===null||draft[k]==='not_selected'||Array.isArray(draft[k])&&draft[k].length===0)))throw new Error();
 return {filled:5-missing.length,missing_fields:missing as string[],ready_for_operator_review:missing.length===0};
}
function parseView(x:unknown,pid:string,repo:string):View{
 if(!record(x))throw new Error();flags(x);
 if(x.project_id!==pid||x.expected_repository!==repo||!integer(x.version)||!integer(x.latest_version)||x.version>x.latest_version
  ||x.state!==(x.version===x.latest_version?'CURRENT':'HISTORICAL')||typeof x.draft_digest!=='string'||!hex.test(x.draft_digest)
  ||!Array.isArray(x.history)||x.history.length<1||x.history.length>10)throw new Error();
 const draft=parseDraft(x.draft),review=parseReview(x.review,draft);
 const latest=x.latest_version;let previous=501;
 const history=x.history.map((v:unknown)=>{
  if(!record(v)||!integer(v.version)||v.version>=previous||v.version>latest
   ||typeof v.draft_digest!=='string'||!hex.test(v.draft_digest))throw new Error();
  previous=v.version;return {version:v.version,draft_digest:v.draft_digest};
 });
 if(history[history.length-1].version!==0||x.latest_version>0&&history[0].version!==x.latest_version)throw new Error();
 return {version:x.version,latest_version:x.latest_version,draft,draft_digest:x.draft_digest,review,history};
}
function toForm(d:Draft):Form{return {revision:d.repository_revision??'',verification:d.verification_kind,
 delivery:d.delivery_kind,target:d.deployment_target??'',acceptance:d.acceptance.join('\n')}}
function toDraft(f:Form):Draft{return {repository_revision:f.revision||null,verification_kind:f.verification,
 delivery_kind:f.delivery,deployment_target:f.target||null,acceptance:f.acceptance.split('\n').map(v=>v.trim()).filter(Boolean)}}

export function ProjectSetup({projectId,label,repository,request,onSaved}:{projectId:string;label:string;repository:string;
 request:Request;onSaved:()=>Promise<void>}){
 const [view,setView]=useState<View|null>(null),[form,setForm]=useState<Form|null>(null);
 const [preview,setPreview]=useState<Preview|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [previewError,setPreviewError]=useState('');
 const generation=useRef(0),active=useRef<AbortController|null>(null);
 const path='projects/'+projectId+'/setup';
 const load=useCallback(async(selected?:number)=>{
  const current=++generation.current;active.current?.abort();const controller=new AbortController();active.current=controller;
  setBusy(true);setError('');setPreviewError('');setNotice('');setView(null);setForm(null);setPreview(null);
  const timer=window.setTimeout(()=>controller.abort(),10000);
  try{
   const next=parseView(await request(path+(selected===undefined?'':'?version='+selected),undefined,controller.signal),projectId,repository);
   if(generation.current===current){setView(next);setForm(toForm(next.draft))}
  }catch{if(generation.current===current)setError('Черновик недоступен. Загрузите сохранённую версию; очередь запросов работает отдельно.')}
  finally{window.clearTimeout(timer);controller.abort();if(generation.current===current)setBusy(false)}
 },[request,path,projectId,repository]);
 useEffect(()=>{void load();return()=>{++generation.current;active.current?.abort()}},[load]);
 function change(value:Partial<Form>){setForm(old=>old?{...old,...value}:old);setPreview(null);setPreviewError('');setNotice('')}
 async function action(kind:'preview'|'save'|'restore'){
  if(!view||!form||busy||error)return;
  const current=generation.current,controller=new AbortController();active.current=controller;
  const timer=window.setTimeout(()=>controller.abort(),10000);
  const candidate=toDraft(form),operation=crypto.randomUUID();
  setBusy(true);setNotice('');setPreviewError('');if(kind==='preview')setPreview(null);
  try{
   if(kind==='preview'){
    const value=await request(path+'/preview',{expected_version:view.version,draft:candidate},controller.signal);
    if(!record(value))throw new Error();flags(value);
    const proposed=parseDraft(value.draft),review=parseReview(value.review,proposed);
    if(value.project_id!==projectId||value.base_version!==view.version||value.stored!==false
     ||typeof value.proposed_digest!=='string'||!hex.test(value.proposed_digest)||!same(proposed,candidate)
     ||!same(value.changed_fields,fields.filter(k=>!same(candidate[k],view.draft[k]))))throw new Error();
    if(current===generation.current)setPreview({draft:proposed,review,proposed_digest:value.proposed_digest,changed_fields:value.changed_fields as string[]});
   }else{
    if(kind==='save'&&(!preview||view.version!==view.latest_version||!same(preview.draft,candidate)))throw new Error();
    const body=kind==='save'?{expected_version:view.version,draft:candidate,operation_id:operation}
     :{expected_version:view.latest_version,target_version:view.version,target_digest:view.draft_digest,operation_id:operation};
    const value=await request(path+(kind==='restore'?'/restore':''),body,controller.signal);
    const expectedDigest=kind==='restore'?view.draft_digest:preview!.proposed_digest;
    if(!record(value)||value.scope!=='SETUP_DRAFT_ONLY'||value.project_id!==projectId||value.operation_id!==operation
     ||value.version!==view.latest_version+1||value.draft_digest!==expectedDigest||value.stored!==true
     ||value.execution_started!==false||value.external_checks_performed!==false)throw new Error();
    if(current===generation.current){
     await onSaved();
     if(current===generation.current){await load();if(generation.current===current+1)setNotice('Черновик сохранён. Подключения и выполнение не включены.')}
    }
   }
  }catch{if(current===generation.current){
   if(kind==='preview')setPreviewError('Предпросмотр не подтверждён. Проверьте поля; если черновик изменился, загрузите сохранённую версию.');
   else setError('Сохранение не подтверждено. Загрузите сохранённую версию перед следующей записью.');
  }}
  finally{window.clearTimeout(timer);controller.abort();if(current===generation.current)setBusy(false)}
 }
 const historical=view!==null&&view.version!==view.latest_version;
 const dirty=view!==null&&form!==null&&!same(toDraft(form),view.draft);
 const disabled=busy||Boolean(error)||historical;
 const prefix='setup-'+projectId+'-';
 return <section className="project-setup" aria-label={'Черновик подключения: '+label} aria-busy={busy}>
  <h3>Черновик подключения</h3>
  <p>Здесь сохраняется план настроек. Ключи, пароли и клиентские данные не вводите.</p>
  {busy&&<p role="status">Обрабатываем черновик…</p>}{(error||previewError)&&<p role="alert">{error||previewError}</p>}{notice&&<p role="status">{notice}</p>}
  {view&&form&&<>
   <p>Версия черновика: {view.version}. Текущая сохранённая версия: {view.latest_version}.</p>
   <p>Заполнено {view.review.filled} из 5. {view.review.ready_for_operator_review?'Черновик заполнен. Нужна проверка подключений.':'Заполните недостающие сведения.'}</p>
   {view.review.missing_fields.length>0&&<ul>{view.review.missing_fields.map(k=><li key={k}>Нужно заполнить: {names[k]}.</li>)}</ul>}
   {historical&&<p>Просмотр прежней версии. Восстановление создаст новую версию черновика.</p>}
   <fieldset disabled={disabled}>
    <label htmlFor={prefix+'revision'}>Версия кода (полный SHA коммита)</label>
    <input id={prefix+'revision'} value={form.revision} maxLength={40} autoComplete="off" spellCheck={false} onChange={e=>change({revision:e.target.value})}/>
    <label htmlFor={prefix+'verification'}>Тип среды проверки</label>
    <select id={prefix+'verification'} value={form.verification} onChange={e=>change({verification:e.target.value as Draft['verification_kind']})}>
     <option value="not_selected">Не выбран</option><option value="python">Python</option><option value="node">Node.js</option><option value="python_node">Python и Node.js</option>
    </select>
    <label htmlFor={prefix+'delivery'}>Способ проверки доставки</label>
    <select id={prefix+'delivery'} value={form.delivery} onChange={e=>change({delivery:e.target.value as Draft['delivery_kind']})}>
     <option value="not_selected">Не выбран</option><option value="manual_review">Ручная проверка</option><option value="pipeline_review">Проверка канала</option>
    </select>
    <label htmlFor={prefix+'target'}>Метка сервера</label>
    <input id={prefix+'target'} value={form.target} placeholder="lnauto-staging" maxLength={48} autoComplete="off" onChange={e=>change({target:e.target.value})}/>
    <label htmlFor={prefix+'acceptance'}>Критерии результата (до 8 строк)</label>
    <textarea id={prefix+'acceptance'} value={form.acceptance} maxLength={1600} onChange={e=>change({acceptance:e.target.value})}/>
    <button disabled={!dirty} onClick={()=>void action('preview')}>Проверить черновик</button>
    <button disabled={!preview||!dirty} onClick={()=>void action('save')}>Сохранить черновик</button>
   </fieldset>
   {preview&&<div role="region" aria-label="Предпросмотр черновика"><p>Будут изменены: {preview.changed_fields.map(k=>names[k]).join(', ')||'нет изменений'}.</p>
    <p>После сохранения заполнено {preview.review.filled} из 5. Подключения ещё потребуют внешней проверки.</p></div>}
   <h4>Обязательные проверки после подготовки</h4>
   <ul><li>Доступ к репозиторию и точной версии кода.</li><li>Сборка и тесты в изолированной среде.</li>
    <li>Привязка канала доставки к серверу.</li><li>Отдельное разрешение задачи и расходов.</li></ul>
   <h4>История черновика</h4>
   <div className="setup-history">{view.history.map(v=><button key={v.version} disabled={busy||dirty||v.version===view.version}
    onClick={()=>void load(v.version)}>Версия {v.version}</button>)}</div>
   {historical&&<button disabled={busy||Boolean(error)} onClick={()=>void action('restore')}>Восстановить версию {view.version} как новый черновик</button>}
  </>}
  <button disabled={busy} onClick={()=>void load()}>Загрузить сохранённый черновик</button>
 </section>
}

export function ProjectSetupOverview({request,revision}:{request:Request;revision:number}){
 const [rows,setRows]=useState<{id:string;label:string;version:number;review:Review}[]|null>(null),[error,setError]=useState(false);
 useEffect(()=>{
  const controller=new AbortController();let current=true;setRows(null);setError(false);
  const timer=window.setTimeout(()=>controller.abort(),10000);
  void (async()=>{
   try{
    const value=await request('project-setup',undefined,controller.signal);
    if(!record(value))throw new Error();flags(value);
    if(!Array.isArray(value.projects)||value.projects.length!==4)throw new Error();
    const next=value.projects.map((v:unknown,i)=>{
     if(!record(v)||v.project_id!==ids[i]||typeof v.label!=='string'||v.label.length>64||!integer(v.version))throw new Error();
     return {id:ids[i],label:v.label,version:v.version,review:parseReview(v.review)};
    });
    if(current)setRows(next);
   }catch{if(current)setError(true)}finally{window.clearTimeout(timer)}
  })();
  return()=>{current=false;controller.abort();window.clearTimeout(timer)};
 },[request,revision]);
 return <div role="region" aria-label="Подготовка подключений"><h3>Подготовка подключений</h3>
  {error?<p role="alert">Сводка черновиков недоступна. Очередь запросов работает отдельно.</p>:rows?<ul>{rows.map(v=><li key={v.id}>
   {v.label}: черновик {v.version}, заполнено {v.review.filled} из 5.</li>)}</ul>:<p role="status">Загружаем сводку черновиков…</p>}
  <p>Полнота черновика не подтверждает доступ к проекту. Форму и историю можно открыть ниже.</p>
 </div>
}
