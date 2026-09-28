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
  const maxBatchItems=Number(dropZone.dataset.maxBatchItems)||50;
  let pending=[];
  let running=false;

  const toast=message=>typeof showToast==='function'?showToast(message):null;
  const escapeHtml=value=>String(value).replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  async function api(url,options={}){
    options.headers={...(options.headers||{}),'X-CSRF-Token':CSRF_TOKEN};
    const response=await fetch(url,options);
    let data={};
    try{data=await response.json();}catch{}
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Permintaan gagal.');
    return data;
  }

  function render(){
    selection.classList.toggle('hidden',!pending.length);
    startButton.textContent=`Proses ${pending.length} PDF`;
    startButton.disabled=running||!pending.length;
    queueHint.textContent=pending.length?`${pending.length} PDF siap diproses satu per satu.`:'Antrean kosong.';
    uploadHint.textContent=pending.length?`${pending.length} PDF siap. Tambahkan lagi atau mulai proses.`:`Atau pilih PDF dari perangkat. Maksimal ${maxBatchItems} dokumen, masing-masing 8 MB.`;
    queueList.innerHTML=pending.map((item,index)=>`<div class="queue-item"><b>${index+1}</b><div><strong>${escapeHtml(item.filename)}</strong><small>${(item.blob.size/1048576).toFixed(2)} MB - PDF teks</small></div><button class="queue-remove" data-index="${index}" type="button" aria-label="Hapus ${escapeHtml(item.filename)}">Hapus</button></div>`).join('');
    queueList.querySelectorAll('.queue-remove').forEach(button=>button.onclick=()=>{
      if(running)return;
      pending.splice(Number(button.dataset.index),1);
      render();
    });
  }

  async function add(files){
    const incoming=[...files];
    const available=maxBatchItems-pending.length;
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
        pending.push(item);
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
    const needed=items.reduce((total,item)=>total+item.blob.size,0);
    if(Number.isFinite(estimate.quota)&&Number.isFinite(estimate.usage)&&estimate.usage+needed>estimate.quota){
      throw new Error('Penyimpanan lokal tidak cukup untuk menyimpan antrean ini. Kosongkan ruang disk lalu coba lagi.');
    }
  }

  async function storeBatchItems(batch){
    const itemIds=[];
    for(const batchItem of batch.items){
      const item=pending.shift();
      if(!item)throw new Error('Antrean berubah sebelum seluruh dokumen disimpan. Silakan coba lagi.');
      const record={id:batchItem.id,batchId:batch.id,filename:item.filename,blob:item.blob,sourceType:'pdf'};
      try{
        await QueueDB.put(record);
      }catch(error){
        pending.unshift(item);
        throw new Error('Antrean tidak dapat disimpan di perangkat ini. Kosongkan ruang disk lalu coba lagi.');
      }
      itemIds.push(record.id);
      render();
    }
    return itemIds;
  }

  async function process(itemIds){
    progress.classList.remove('hidden');
    let position=0;
    for(const itemId of itemIds){
      const item=await QueueDB.get(itemId);
      if(!item)continue;
      position++;
      progress.textContent=`Memproses ${position} dari ${itemIds.length}: ${item.filename}`;
      const formData=new FormData();
      formData.append('file',item.blob,item.filename);
      try{
        const result=await api(`/api/scan-items/${item.id}/process`,{method:'POST',body:formData});
        if(result.status!=='FAILED'||['DUPLICATE_DOCUMENT','DUPLICATE_HOUSEHOLD'].includes(result.failure_code))await QueueDB.remove(item.id);
      }catch(error){
        toast(`${item.filename}: ${error.message}`);
      }
    }
  }

  galleryInput.onchange=event=>{add(event.target.files);galleryInput.value='';};
  galleryButton.onclick=event=>{event.stopPropagation();galleryInput.click();};
  dropZone.onclick=()=>galleryInput.click();
  dropZone.onkeydown=event=>{
    if(event.key==='Enter'||event.key===' '){event.preventDefault();galleryInput.click();}
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
    pending=[];
    render();
  };

  startButton.onclick=async()=>{
    if(running||!pending.length)return;
    running=true;
    render();
    try{
      await ensureStorageCapacity(pending);
      const filenames=pending.map(item=>item.filename);
      const batch=await api('/api/batches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filenames})});
      const itemIds=await storeBatchItems(batch);
      await process(itemIds);
      location.href=`/batches/${batch.id}`;
    }catch(error){
      toast(error.message);
    }finally{
      running=false;
      progress.classList.add('hidden');
      render();
    }
  };

  QueueDB.ids().then(itemIds=>{
    if(!itemIds.length)return;
    resume.classList.remove('hidden');
    resumeButton.textContent=`Lanjutkan ${itemIds.length} PDF`;
    resumeButton.onclick=async()=>{
      if(running)return;
      running=true;
      render();
      try{
        await process(itemIds);
      }finally{
        running=false;
        progress.classList.add('hidden');
        render();
      }
    };
  }).catch(()=>toast('Antrean lokal sebelumnya tidak dapat dibuka.'));
  render();
})();
