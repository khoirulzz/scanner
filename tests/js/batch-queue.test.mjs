import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source=readFileSync(new URL('../../app/static/js/batch-queue.js',import.meta.url),'utf8');

class ClassList{
  constructor(){this.values=new Set();}
  add(name){this.values.add(name);}
  remove(name){this.values.delete(name);}
  toggle(name,force){
    const active=force===undefined?!this.values.has(name):force;
    if(active)this.values.add(name);else this.values.delete(name);
    return active;
  }
  contains(name){return this.values.has(name);}
}

class Element{
  constructor(){
    this.classList=new ClassList();
    this.dataset={};
    this.disabled=false;
    this.innerHTML='';
    this.textContent='';
    this.value='';
    this.listeners={};
  }
  addEventListener(name,callback){this.listeners[name]=callback;}
  querySelectorAll(){return [];}
  contains(){return false;}
  click(){}
}

function response(ok,status,data){
  return {ok,status,json:async()=>data};
}

async function waitFor(predicate){
  const deadline=Date.now()+1000;
  while(!predicate()){
    if(Date.now()>deadline)throw new Error('Timed out waiting for batch queue state.');
    await new Promise(resolve=>setTimeout(resolve,1));
  }
}

function createHarness({count,failAt=0}){
  const ids=['galleryInput','pdfDropZone','uploadHint','selection','queueList','queueHint','clearQueue','galleryBtn','resume','resumeBtn','startBtn','processProgress','batchOutcome','outcomeTitle','outcomeSummary','outcomeLinks'];
  const elements=Object.fromEntries(ids.map(id=>[id,new Element()]));
  elements.pdfDropZone.dataset.maxBatchItems='50';
  elements.selection.classList.add('hidden');
  elements.resume.classList.add('hidden');
  elements.processProgress.classList.add('hidden');
  elements.batchOutcome.classList.add('hidden');
  const removed=[];
  const stored=[];
  let processCalls=0;
  let active=0;
  let maxActive=0;
  const context={
    Blob,
    FormData,
    Promise,
    Set,
    Number,
    String,
    JSON,
    encodeURIComponent,
    setTimeout,
    clearTimeout,
    CSRF_TOKEN:'test-token',
    document:{getElementById:id=>elements[id]},
    navigator:{storage:{estimate:async()=>({quota:1_000_000_000,usage:0})}},
    showToast:()=>{},
    ImagePreprocessor:{prepare:async file=>({filename:file.name,blob:new Blob(['%PDF-test']),sourceType:'pdf'})},
    QueueDB:{
      all:async()=>[],
      putMany:async records=>{stored.push(...records);},
      put:async()=>{},
      remove:async id=>{removed.push(id);},
    },
    fetch:async(url,options)=>{
      if(url==='/api/batches'){
        const filenames=JSON.parse(options.body).filenames;
        return response(true,200,{id:'batch-1',items:filenames.map((filename,index)=>({id:`item-${index+1}`,filename}))});
      }
      processCalls++;
      active++;
      maxActive=Math.max(maxActive,active);
      await new Promise(resolve=>setTimeout(resolve,1));
      active--;
      if(failAt&&processCalls===failAt)return response(false,422,{detail:'Gangguan uji pada PDF.'});
      return response(true,200,{status:'EXTRACTED',failure_message:null});
    },
  };
  vm.runInContext(source,vm.createContext(context));
  const files=Array.from({length:count},(_,index)=>({name:`kk-${index+1}.pdf`}));
  return {elements,files,removed,stored,get processCalls(){return processCalls;},get maxActive(){return maxActive;}};
}

test('memproses 50 PDF satu per satu dan mempertahankan hasil di halaman scan',async()=>{
  const harness=createHarness({count:50});
  harness.elements.galleryInput.onchange({target:{files:harness.files}});
  await waitFor(()=>harness.elements.queueList.innerHTML.includes('kk-50.pdf'));
  await harness.elements.startBtn.onclick();

  assert.equal(harness.stored.length,50);
  assert.equal(harness.processCalls,50);
  assert.equal(harness.maxActive,1);
  assert.equal(harness.removed.length,50);
  assert.equal((harness.elements.queueList.innerHTML.match(/Buka hasil/g)||[]).length,50);
  assert.equal(harness.elements.outcomeTitle.textContent,'Proses batch selesai');
  assert.match(harness.elements.outcomeLinks.innerHTML,/Lihat hasil batch/);
});

test('menghentikan antrean pada kegagalan lokal tanpa melewati PDF berikutnya',async()=>{
  const harness=createHarness({count:5,failAt:3});
  harness.elements.galleryInput.onchange({target:{files:harness.files}});
  await waitFor(()=>harness.elements.queueList.innerHTML.includes('kk-5.pdf'));
  await harness.elements.startBtn.onclick();

  assert.equal(harness.processCalls,3);
  assert.equal(harness.removed.length,2);
  assert.match(harness.elements.queueList.innerHTML,/Dijeda/);
  assert.match(harness.elements.queueList.innerHTML,/Menunggu/);
  assert.equal(harness.elements.outcomeTitle.textContent,'Proses dijeda');
  assert.equal(harness.elements.resume.classList.contains('hidden'),false);
});
