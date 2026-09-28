(()=>{
  const root=document.getElementById('batchList');
  const batchId=root.dataset.batchId;
  const batchCode=root.dataset.batchCode||'Batch';
  const summary=document.getElementById('batchSummary');
  const subtitle=document.getElementById('batchSubtitle');
  const actionHint=document.getElementById('batchActionHint');
  const approveButton=document.getElementById('approveExtracted');
  const reviewNext=document.getElementById('reviewNext');
  const filters=document.getElementById('batchFilters');
  const deleteBatchButton=document.getElementById('deleteBatch');
  let batch=null;
  let filter='';
  const labels={QUEUED:'Menunggu',PROCESSING:'Diproses',EXTRACTED:'Siap disetujui',REVIEW_REQUIRED:'Perlu review',APPROVED:'Disetujui',FAILED:'Gagal'};
  const toast=message=>typeof showToast==='function'?showToast(message):null;
  const escapeHtml=value=>String(value||'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
  async function api(url,options={}){options.headers={...(options.headers||{}),'X-CSRF-Token':CSRF_TOKEN};const response=await fetch(url,options);let data={};try{data=await response.json()}catch{}if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Request gagal');return data}
  const card=(label,value)=>`<div><span>${label}</span><b>${value}</b></div>`;
  function render(){
    subtitle.textContent=`${batch.total} dokumen`;
    summary.innerHTML=[card('Siap disetujui',batch.extracted),card('Perlu review',batch.review_required),card('Disetujui',batch.approved),card('Gagal',batch.failed)].join('');
    approveButton.disabled=!batch.extracted;
    approveButton.textContent=batch.extracted?`Setujui semua (${batch.extracted})`:'Tidak ada data valid';
    const next=batch.items.find(item=>item.status==='REVIEW_REQUIRED')||batch.items.find(item=>item.status==='EXTRACTED');
    reviewNext.href=next?`/scans/${next.id}`:'#';
    reviewNext.classList.toggle('disabled',!next);
    actionHint.textContent=batch.review_required?`${batch.review_required} perlu diperiksa.`:batch.extracted?`${batch.extracted} siap disetujui.`:'Selesai.';
    const items=filter?batch.items.filter(item=>item.status===filter):batch.items;
    root.innerHTML=items.map(item=>`<article class="batch-item" data-item-id="${item.id}"><div><small>KK-${String(item.item_number).padStart(3,'0')}</small><h3>${escapeHtml(item.original_filename)}</h3><p>${item.failure_message?escapeHtml(item.failure_message):labels[item.status]}</p></div><div class="batch-item-actions"><span class="badge badge-${item.status.toLowerCase()}">${labels[item.status]}</span><a class="btn" href="/scans/${item.id}">${item.status==='FAILED'?'Lihat alasan':'Buka'}</a><button class="btn danger-ghost" type="button" data-delete-item="${item.id}">Hapus</button></div></article>`).join('')||'<p class="empty-state">Tidak ada dokumen pada filter ini.</p>';
  }
  async function load(){batch=await api(`/api/batches/${batchId}`);render()}
  filters.querySelectorAll('button').forEach(button=>button.onclick=()=>{filter=button.dataset.filter;filters.querySelectorAll('button').forEach(item=>item.classList.toggle('active',item===button));render()});
  approveButton.onclick=async()=>{if(!batch.extracted)return;approveButton.disabled=true;try{const result=await api(`/api/batches/${batchId}/approve-extracted`,{method:'POST'});batch=result.batch;toast(`${result.approved_count} data disetujui`);render()}catch(error){toast(error.message)}};
  deleteBatchButton.onclick=async()=>{
    const confirmed=await askDangerousAction({title:'Hapus batch?',message:`${batchCode} dan seluruh hasil scan di dalamnya akan dihapus permanen dari database lokal. Riwayat export yang terkait juga akan dibersihkan.`,confirmLabel:'Hapus batch'});
    if(!confirmed)return;
    deleteBatchButton.disabled=true;deleteBatchButton.textContent='Menghapus...';
    try{await api(`/api/batches/${batchId}`,{method:'DELETE'});window.location.href='/batches'}catch(error){deleteBatchButton.disabled=false;deleteBatchButton.textContent='Hapus batch';toast(error.message)}
  };
  root.addEventListener('click',async event=>{
    const button=event.target.closest('[data-delete-item]');
    if(!button)return;
    const item=batch.items.find(row=>row.id===button.dataset.deleteItem);
    if(!item)return;
    const confirmed=await askDangerousAction({title:'Hapus hasil scan?',message:`${item.original_filename} akan dihapus dari database lokal beserta data KK, anggota keluarga, thumbnail, review, dan riwayat yang terkait.`,confirmLabel:'Hapus hasil'});
    if(!confirmed)return;
    const row=button.closest('.batch-item');row?.classList.add('is-deleting');button.disabled=true;button.textContent='Menghapus...';
    try{
      const result=await api(`/api/scan-items/${item.id}`,{method:'DELETE'});
      if(result.batch_deleted){window.location.href='/batches';return}
      toast('Hasil scan dihapus');await load();
    }catch(error){row?.classList.remove('is-deleting');button.disabled=false;button.textContent='Hapus';toast(error.message)}
  });
  load().catch(error=>{root.innerHTML=`<p class="error">${escapeHtml(error.message)}</p>`});
})();
