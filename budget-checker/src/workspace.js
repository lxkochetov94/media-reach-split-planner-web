(function(root,factory){
  const api=factory(root.BudgetExcel,root.BudgetCore);
  if(typeof module==='object'&&module.exports) module.exports=api;
  else root.BudgetWorkspace=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(Excel,Core){
  'use strict';

  const DB_NAME='budget-checker-workspace';
  const DB_VERSION=1;
  const STORE='handles';
  const ROOT_KEY='workspace-root';
  const DIR_BASE='База';
  const DIR_CURRENT='Актуальный';
  const DIR_ARCHIVE='Архив';

  function hasFsAccess(){ return typeof globalThis.showDirectoryPicker==='function'; }
  function safePart(s){ return String(s??'').trim().replace(/[\\/:*?"<>|]+/g,'_').replace(/\s+/g,' ').trim()||'Проект'; }
  function projectFolderName(project){ return `${safePart(project.projectName)} — ${safePart(project.period)}`; }
  function actualFileName(project){ return `${safePart(project.projectName)}_${safePart(project.period)}_АКТУАЛЬНЫЙ.xlsx`; }
  function baseControlFileName(project){ const d=String(project.baseCreatedAt||'').slice(0,10)||new Date().toISOString().slice(0,10); return `BASE_${safePart(project.projectName)}_${safePart(project.period)}_${d}.xlsx`; }
  function sourceCopyFileName(project,sourceFile){ return `ИСТОЧНИК_${safePart(sourceFile?.name||project.sourceFileName||'flowchart.xlsx')}`; }
  function archiveFileName(project,date=new Date()){
    const iso=(date instanceof Date?date:new Date(date)).toISOString();
    const stamp=iso.replace('T','_').replace(/:/g,'-').replace('.', '-');
    const last=[...(project.operations||[])].sort(Core?.opSort||((a,b)=>0)).at(-1)?.number||'BASE';
    return `${safePart(project.projectName)}_${safePart(project.period)}_${stamp}_${safePart(last)}.xlsx`;
  }

  function openDb(){
    if(typeof indexedDB==='undefined') return Promise.resolve(null);
    return new Promise((resolve,reject)=>{
      const req=indexedDB.open(DB_NAME,DB_VERSION);
      req.onupgradeneeded=()=>{ const db=req.result; if(!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE); };
      req.onsuccess=()=>resolve(req.result); req.onerror=()=>reject(req.error);
    });
  }
  async function rememberRootHandle(handle){ const db=await openDb(); if(!db)return; await new Promise((resolve,reject)=>{ const tx=db.transaction(STORE,'readwrite'); tx.objectStore(STORE).put(handle,ROOT_KEY); tx.oncomplete=resolve; tx.onerror=()=>reject(tx.error); }); db.close(); }
  async function loadRootHandle(){ const db=await openDb(); if(!db)return null; const val=await new Promise((resolve,reject)=>{ const tx=db.transaction(STORE,'readonly'); const req=tx.objectStore(STORE).get(ROOT_KEY); req.onsuccess=()=>resolve(req.result||null); req.onerror=()=>reject(req.error); }); db.close(); return val; }
  async function forgetRootHandle(){ const db=await openDb(); if(!db)return; await new Promise((resolve,reject)=>{ const tx=db.transaction(STORE,'readwrite'); tx.objectStore(STORE).delete(ROOT_KEY); tx.oncomplete=resolve; tx.onerror=()=>reject(tx.error); }); db.close(); }

  async function ensurePermission(handle,{request=false}={}){
    if(!handle) return false;
    const opts={mode:'readwrite'};
    if(typeof handle.queryPermission==='function'){
      const q=await handle.queryPermission(opts); if(q==='granted')return true; if(!request)return false;
    }
    if(request&&typeof handle.requestPermission==='function') return (await handle.requestPermission(opts))==='granted';
    return true;
  }
  async function chooseWorkspace(){
    if(!hasFsAccess()) throw new Error('Браузер не поддерживает выбор рабочей папки. Используйте актуальный Chrome или Edge по HTTPS.');
    const handle=await globalThis.showDirectoryPicker({mode:'readwrite',id:'budget-checker-workspace'});
    if(!(await ensurePermission(handle,{request:true}))) throw new Error('Нет разрешения на запись в рабочую папку.');
    await rememberRootHandle(handle); return handle;
  }

  async function getDirs(root,project,{create=false}={}){
    const folder=project.workspaceFolderName||projectFolderName(project);
    const projectDir=await root.getDirectoryHandle(folder,{create});
    const baseDir=await projectDir.getDirectoryHandle(DIR_BASE,{create});
    const currentDir=await projectDir.getDirectoryHandle(DIR_CURRENT,{create});
    const archiveDir=await projectDir.getDirectoryHandle(DIR_ARCHIVE,{create});
    return {folder,projectDir,baseDir,currentDir,archiveDir};
  }
  async function fileExists(dir,name){ try{ await dir.getFileHandle(name,{create:false}); return true; }catch(e){ if(e&&e.name==='NotFoundError')return false; throw e; } }
  async function writeBytes(dir,name,bytes,{overwrite=true}={}){
    if(!overwrite&&await fileExists(dir,name)) throw new Error(`Файл уже существует: ${name}`);
    const fh=await dir.getFileHandle(name,{create:true});
    const w=await fh.createWritable();
    try{ await w.write(bytes); await w.close(); }catch(e){ try{await w.abort?.();}catch(_){} throw e; }
    return fh;
  }
  async function writeProject(dir,name,project,{overwrite=true}={}){
    if(!Excel||typeof Excel.projectWorkbookBytes!=='function') throw new Error('Модуль Excel не готов к сохранению в рабочую папку.');
    const bytes=Excel.projectWorkbookBytes(project,[]);
    return writeBytes(dir,name,bytes,{overwrite});
  }

  async function initializeProject(root,project,sourceFile){
    if(!(await ensurePermission(root,{request:true}))) throw new Error('Нет разрешения на запись в рабочую папку.');
    project.workspaceFolderName=project.workspaceFolderName||projectFolderName(project);
    const folder=project.workspaceFolderName;
    let existing=null;
    try{ existing=await root.getDirectoryHandle(folder,{create:false}); }catch(e){ if(e?.name!=='NotFoundError')throw e; }
    if(existing) throw new Error('Папка проекта «'+folder+'» уже существует. Выберите другое название/период или откройте существующий проект.');
    try{
      const dirs=await getDirs(root,project,{create:true});
      const actualName=actualFileName(project),baseName=baseControlFileName(project),sourceName=sourceCopyFileName(project,sourceFile);
      if(sourceFile){ const sourceBytes=await sourceFile.arrayBuffer(); await writeBytes(dirs.baseDir,sourceName,sourceBytes,{overwrite:false}); }
      await writeProject(dirs.baseDir,baseName,project,{overwrite:false});
      const currentHandle=await writeProject(dirs.currentDir,actualName,project,{overwrite:true});
      await writeProject(dirs.archiveDir,archiveFileName(project),project,{overwrite:false});
      return {...dirs,currentHandle,actualName,baseName,sourceName};
    }catch(e){ try{ await root.removeEntry?.(folder,{recursive:true}); }catch(_){} throw e; }
  }

  async function persistProject(project,projectDir,{archive=true}={}){
    if(!(await ensurePermission(projectDir,{request:false}))) throw new Error('Браузер потерял разрешение на папку проекта. Вернитесь к списку проектов и снова разрешите доступ к рабочей папке.');
    const currentDir=await projectDir.getDirectoryHandle(DIR_CURRENT,{create:true});
    const archiveDir=await projectDir.getDirectoryHandle(DIR_ARCHIVE,{create:true});
    const name=actualFileName(project);
    project.lastSavedAt=new Date().toISOString();
    const currentHandle=await writeProject(currentDir,name,project,{overwrite:true});
    let archiveWarning='';
    if(archive){
      try{ await writeProject(archiveDir,archiveFileName(project),project,{overwrite:false}); }
      catch(e){ archiveWarning=`Актуальный файл сохранён, но архивный снимок создать не удалось: ${e.message}`; }
    }
    return {currentHandle,fileName:name,archiveWarning};
  }

  async function readProjectFromFileHandle(fileHandle){
    const file=await fileHandle.getFile();
    const data=await Excel.readWorkbookFile(file);
    const parsed=Excel.workbookToProject(data);
    return {file,data,...parsed};
  }

  async function findActualFile(projectDir){
    let currentDir;
    try{ currentDir=await projectDir.getDirectoryHandle(DIR_CURRENT,{create:false}); }catch(e){return null;}
    let fallback=null;
    for await(const entry of currentDir.values()){
      if(entry.kind!=='file'||!/\.xlsx$/i.test(entry.name))continue;
      if(entry.name.includes('_АКТУАЛЬНЫЙ.xlsx')) return {currentDir,fileHandle:entry};
      fallback=fallback||entry;
    }
    return fallback?{currentDir,fileHandle:fallback}:null;
  }

  async function scanProjects(root){
    if(!(await ensurePermission(root,{request:false}))) return {projects:[],permissionRequired:true,errors:[]};
    const projects=[],errors=[];
    for await(const entry of root.values()){
      if(entry.kind!=='directory')continue;
      try{
        const found=await findActualFile(entry); if(!found)continue;
        const parsed=await readProjectFromFileHandle(found.fileHandle);
        const project=parsed.project; project.workspaceFolderName=project.workspaceFolderName||entry.name;
        const tree=Core.aggregateTree(project);
        const control=[...Core.validateProject(project),...parsed.issues];
        const lastOp=[...(project.operations||[])].sort(Core.opSort).at(-1)||null;
        projects.push({folderName:entry.name,projectDir:entry,currentDir:found.currentDir,fileHandle:found.fileHandle,project,issues:parsed.issues,tree,lastOp,errorCount:control.filter(x=>x.severity==='error').length});
      }catch(e){ errors.push({folderName:entry.name,message:e.message}); }
    }
    projects.sort((a,b)=>String(a.project.projectName).localeCompare(String(b.project.projectName),'ru')||String(a.project.period).localeCompare(String(b.project.period)));
    return {projects,permissionRequired:false,errors};
  }

  return {DIR_BASE,DIR_CURRENT,DIR_ARCHIVE,hasFsAccess,safePart,projectFolderName,actualFileName,baseControlFileName,sourceCopyFileName,archiveFileName,rememberRootHandle,loadRootHandle,forgetRootHandle,ensurePermission,chooseWorkspace,getDirs,fileExists,writeBytes,initializeProject,persistProject,readProjectFromFileHandle,scanProjects};
});
