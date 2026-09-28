(()=>{
  const galleryInput=document.getElementById('galleryInput');
  const dropZone=document.getElementById('pdfDropZone');
  const uploadHint=document.getElementById('uploadHint');
  const selection=document.getElementById('selection');
  const queueList=document.getElementById('queueList');
  const queueHint=document.getElementById('queueHint');
  const clearQueue=document.getElementById('clearQueue');
  const galleryButton=document.getElementById('galleryBtn');
  const resume=document.getElementById('resume');
  const resumeButton=document.getElementById('resumeBtn');
  const startButton=document.getElementById('startBtn');
  const progress=document.getElementById('processProgress');
  const outcome=document.getElementById('batchOutcome');
  const outcomeTitle=document.getElementById('outcomeTitle');
  const outcomeSummary=document.getElementById('outcomeSummary');
  const outcomeLinks=document.getElementById('outcomeLinks');
  const maxBatchItems=Number(dropZone.dataset.maxBatchItems)||50;
  const terminalStatuses=new Set(['EXTRACTED','REVIEW_REQUIRED','APPROVED','FAILED']);
  const statusLabels={
    READY:'Menunggu',
    PAUSED:'Dijeda',
    PROCESSING:'Memproses',
    EXTRACTED:'Siap diperiksa',
    REVIEW_REQUIRED:'Perlu diperiksa',
    APPROVED:'Disetujui',
    FAILED:'Gagal',
  };
  let queue=[];
  let running=false;
  let restorePromise=Promise.resolve();

  const toast=message=>typeof showToast==='function'?showToast(message):null;
  const escapeHtml=value=>String(value).replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  const wait=milliseconds=>new Promise(resolve=>setTimeout(resolve,milliseconds));
  const isTerminal=item=>terminalStatuses.has(item.status);
  const unfinishedItems=()=>queue.filter(item=>item.id&&!isTerminal(item));

  async function api(url,options={}){
    options.headers={...(options.headers||{}),'X-CSRF-Token':CSRF_TOKEN};
    let response;
    try{
      response=await fetch(url,options);
    }catch(cause){
      const error=new Error('Server lokal tidak dapat dihubungi.');
      error.retryable=true;
      error.cause=cause;
      throw error;
    }
    let data={};
    try{data=await response.json();}catch{}
    if(!response.ok){
      const detail=typeof data.detail==='string'?data.detail:'Permintaan gagal.';
      const error=new Error(detail);
      error.retryable=response.status===429||response.status>=500;
      error.status=response.status;
      throw error;
    }
    return data;
  }

  function render(){
    const hasQueue=queue.length>0;
    const hasServerItems=queue.some(item=>item.id);
    const allFinished=hasQueue&&queue.every(isTerminal);
    const recoverable=unfinishedItems();
    selection.classList.toggle('hidden',!hasQueue);
    startButton.classList.toggle('hidden',hasServerItems||allFinished);
    clearQueue.classList.toggle('hidden',hasServerItems&&!allFinished);
    startButton.textContent=`Proses ${queue.length} PDF`;
    startButton.disabled=running||!hasQueue||hasServerItems;
    clearQueue.disabled=running;
    resume.classList.toggle('hidden',running||recoverable.length===0);
    resumeButton.textContent=`Lanjutkan ${recoverable.length} PDF`;
    if(running){
      queueHint.textContent=`Memproses ${queue.length} PDF secara berurutan. Jangan tutup aplikasi.`;
    }else if(allFinished){
      queueHint.textContent='Semua dokumen sudah diproses. Buka hasilnya langsung dari daftar di bawah.';
    }else if(hasServerItems){
      queueHint.textContent=`${recoverable.length} PDF belum selesai dan aman untuk dilanjutkan.`;
    }else{
      queueHint.textContent=`${queue.length} PDF siap diproses satu per satu.`;
    }
    uploadHint.textContent=hasQueue&&!allFinished
      ?`${queue.length} PDF sudah berada dalam antrean.`
      :`Atau pilih PDF dari perangkat. Maksimal ${maxBatchItems} dokumen, masing-masing 8 MB.`;
    queueList.innerHTML=queue.map((item,index)=>{
      const size=item.blob&&Number.isFinite(item.blob.size)?`${(item.blob.size/1048576).toFixed(2)} MB`:'Ukuran tidak tersedia';
      const status=item.status||'READY';
      const message=item.message?`<small>${escapeHtml(item.message)}</small>`:`<small>${size} - PDF teks</small>`;
      const resultLink=item.id&&isTerminal(item)?`<a class="queue-result-link" href="/scans/${encodeURIComponent(item.id)}">Buka hasil</a>`:'';
      const removeButton=!item.id&&!running?`<button class="queue-remove" data-index="${index}" type="button" aria-label="Hapus ${escapeHtml(item.filename)}">Hapus</button>`:'';
      return `<div class="queue-item queue-item-${status.toLowerCase()}"><b>${index+1}</b><div class="queue-item-main"><strong>${escapeHtml(item.filename)}</strong>${message}</div><div class="queue-item-state"><span class="queue-status queue-status-${status.toLowerCase()}">${statusLabels[status]||escapeHtml(status)}</span>${resultLink}${removeButton}</div></div>`;
    }).join('');
    queueList.querySelectorAll('.queue-remove').forEach(button=>button.onclick=()=>{
      if(running)return;
      queue.splice(Number(button.dataset.index),1);
      render();
    });
  }

  function renderOutcome(paused=false){
    const serverItems=queue.filter(item=>item.id);
    if(!serverItems.length){
      outcome.classList.add('hidden');
      return;
    }
    const finished=serverItems.filter(isTerminal).length;
    const failed=serverItems.filter(item=>item.status==='FAILED').length;
    const successful=serverItems.filter(item=>['EXTRACTED','REVIEW_REQUIRED','APPROVED'].includes(item.status)).length;
    outcome.classList.remove('hidden');
    outcome.classList.toggle('is-paused',paused);
    outcomeTitle.textContent=paused?'Proses dijeda':'Proses batch selesai';
    outcomeSummary.textContent=paused
      ?`${finished} dari ${serverItems.length} PDF sudah selesai. Perbaiki kendala yang ditandai, lalu lanjutkan antrean.`
      :`${successful} PDF berhasil dibaca${failed?`, ${failed} gagal dan perlu diperiksa`:''}. Hasil tetap tampil di halaman ini.`;
    const batchIds=[...new Set(serverItems.map(item=>item.batchId).filter(Boolean))];
    outcomeLinks.innerHTML=batchIds.map((batchId,index)=>`<a class="btn primary" href="/batches/${encodeURIComponent(batchId)}">${batchIds.length===1?'Lihat hasil batch':`Lihat batch ${index+1}`}</a>`).join('');
  }

  function canAddFiles(){
    if(running)return false;
    if(unfinishedItems().length){
      toast('Selesaikan atau lanjutkan antrean sebelumnya sebelum membuat batch baru.');
      return false;
    }
    if(queue.length&&queue.every(isTerminal)){
      queue=[];
      outcome.classList.add('hidden');
      render();
    }
    return true;
  }

  async function add(files){
    await restorePromise;
    if(!canAddFiles())return;
    const incoming=[...files];
    const available=maxBatchItems-queue.length;
    if(available<=0){
      toast(`Maksimal ${maxBatchItems} dokumen dalam satu batch.`);
      return;
    }
    const candidates=incoming.slice(0,available);
    if(candidates.length<incoming.length)toast(`Hanya ${available} dokumen yang ditambahkan agar batch maksimal ${maxBatchItems} PDF.`);
    let added=0;
    for(const file of candidates){
      try{
        const item=await ImagePreprocessor.prepare(file);
        if(item.sourceType!=='pdf')throw new Error('Gunakan PDF KK dengan teks selectable.');
        queue.push({...item,status:'READY',message:''});
        added++;
      }catch(error){toast(error.message);}
    }
    if(added)render();
  }

  function setDragging(active){
    dropZone.classList.toggle('is-dragging',active);
    if(active)uploadHint.textContent='Lepaskan PDF untuk menambahkannya ke antrean.';
  }

  async function ensureStorageCapacity(items){
    if(!navigator.storage||typeof navigator.storage.estimate!=='function')return;
    const estimate=await navigator.storage.estimate();
    const needed=items.reduce((total,item)=>total+(item.blob?.size||0),0);
    if(Number.isFinite(estimate.quota)&&Number.isFinite(estimate.usage)&&estimate.usage+needed>estimate.quota){
      throw new Error('Penyimpanan lokal tidak cukup untuk menyimpan antrean ini. Kosongkan ruang disk lalu coba lagi.');
    }
  }

  async function attachBatch(batch){
    if(batch.items.length!==queue.length)throw new Error('Jumlah dokumen dari server tidak sesuai dengan antrean. Muat ulang aplikasi lalu coba kembali.');
    const records=batch.items.map((batchItem,index)=>({
      id:batchItem.id,
      batchId:batch.id,
      filename:queue[index].filename,
      blob:queue[index].blob,
      sourceType:'pdf',
      status:'READY',
      message:'Menunggu giliran diproses.',
      stored:true,
    }));
    try{
      await QueueDB.putMany(records);
    }catch(error){
      records.forEach(record=>{record.stored=false;});
      toast('Pemulihan antrean setelah restart tidak tersedia, tetapi batch ini tetap akan diproses sekarang.');
    }
    queue=records;
    render();
    return records;
  }

  async function processRequest(item,position,total){
    let lastError;
    for(let attempt=1;attempt<=3;attempt++){
      try{
        const formData=new FormData();
        formData.append('file',item.blob,item.filename);
        return await api(`/api/scan-items/${encodeURIComponent(item.id)}/process`,{method:'POST',body:formData});
      }catch(error){
        lastError=error;
        if(!error.retryable||attempt===3)throw error;
        const delay=attempt===1?600:1500;
        progress.textContent=`Koneksi terganggu pada PDF ${position} dari ${total}. Mencoba lagi...`;
        await wait(delay);
      }
    }
    throw lastError;
  }

  async function processRecords(records){
    progress.classList.remove('hidden');
    outcome.classList.add('hidden');
    let pausedItem=null;
    for(const item of records){
      if(isTerminal(item))continue;
      const position=queue.indexOf(item)+1;
      try{
        if(!(item.blob instanceof Blob))throw new Error('Salinan PDF lokal tidak ditemukan. Pilih ulang dokumen ini.');
        item.status='PROCESSING';
        item.message='Sedang membaca data KK...';
        progress.textContent=`Memproses ${position} dari ${queue.length}: ${item.filename}`;
        render();
        const result=await processRequest(item,position,queue.length);
        item.status=result.status||'FAILED';
        item.message=result.failure_message||(item.status==='REVIEW_REQUIRED'?'Data terbaca dan perlu diperiksa.':'Data KK berhasil dibaca.');
        if(item.stored!==false){
          try{
            await QueueDB.remove(item.id);
            item.stored=false;
          }catch{
            item.message+=' Hasil sudah aman di aplikasi, tetapi salinan antrean lokal belum dapat dibersihkan.';
          }
        }
        render();
      }catch(error){
        item.status='PAUSED';
        item.message=error.message||'Pemrosesan terhenti. Silakan lanjutkan kembali.';
        pausedItem=item;
        if(item.stored!==false){
          try{await QueueDB.put(item);}catch{}
        }
        render();
        toast(`${item.filename}: ${item.message}`);
        break;
      }
    }
    progress.classList.add('hidden');
    renderOutcome(Boolean(pausedItem));
    return !pausedItem;
  }

  function openPicker(event){
    if(event)event.stopPropagation();
    if(canAddFiles())galleryInput.click();
  }

  galleryInput.onchange=event=>{add(event.target.files);galleryInput.value='';};
  galleryButton.onclick=openPicker;
  dropZone.onclick=openPicker;
  dropZone.onkeydown=event=>{
    if(event.key==='Enter'||event.key===' '){event.preventDefault();openPicker(event);}
  };
  for(const eventName of ['dragenter','dragover'])dropZone.addEventListener(eventName,event=>{
    event.preventDefault();
    event.stopPropagation();
    setDragging(true);
  });
  for(const eventName of ['dragleave','dragend'])dropZone.addEventListener(eventName,event=>{
    event.preventDefault();
    event.stopPropagation();
    if(!dropZone.contains(event.relatedTarget))setDragging(false);
  });
  dropZone.addEventListener('drop',event=>{
    event.preventDefault();
    event.stopPropagation();
    setDragging(false);
    add(event.dataTransfer.files);
  });
  clearQueue.onclick=()=>{
    if(running)return;
    if(unfinishedItems().length){
      toast('Antrean yang belum selesai tidak dapat dikosongkan dari sini. Lanjutkan proses atau hapus batch dari halaman Hasil.');
      return;
    }
    queue=[];
    outcome.classList.add('hidden');
    render();
  };

  startButton.onclick=async()=>{
    if(running||!queue.length||queue.some(item=>item.id))return;
    running=true;
    render();
    try{
      await ensureStorageCapacity(queue);
      const filenames=queue.map(item=>item.filename);
      const batch=await api('/api/batches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filenames})});
      const records=await attachBatch(batch);
      await processRecords(records);
    }catch(error){
      toast(error.message);
    }finally{
      running=false;
      progress.classList.add('hidden');
      render();
    }
  };

  resumeButton.onclick=async()=>{
    if(running)return;
    const records=unfinishedItems();
    if(!records.length)return;
    running=true;
    records.forEach(item=>{if(item.status==='PAUSED')item.status='READY';});
    render();
    try{
      await processRecords(records);
    }finally{
      running=false;
      progress.classList.add('hidden');
      render();
    }
  };

  restorePromise=QueueDB.all().then(async records=>{
    const stale=records.filter(item=>terminalStatuses.has(item.status));
    await Promise.allSettled(stale.map(item=>QueueDB.remove(item.id)));
    queue=records.filter(item=>item.id&&item.blob&&!terminalStatuses.has(item.status)).map(item=>({
      ...item,
      status:'PAUSED',
      message:'Antrean dipulihkan dan siap dilanjutkan.',
      stored:true,
    }));
    if(queue.length){
      render();
      renderOutcome(true);
    }
  }).catch(()=>toast('Antrean lokal sebelumnya tidak dapat dibuka.'));
  render();
})();
