(()=>{
  const root=document.getElementById('batchHistory');
  if(!root)return;
  const escapeDetail=data=>typeof data?.detail==='string'?data.detail:'Permintaan gagal.';
  async function removeBatch(card,button){
    const batchId=card.dataset.batchId;
    const batchCode=card.dataset.batchCode||'batch ini';
    const confirmed=await askDangerousAction({
      title:'Hapus batch?',
      message:`${batchCode} dan seluruh hasil scan di dalamnya akan dihapus dari database lokal. Riwayat export yang terkait juga akan dibersihkan. Tindakan ini tidak dapat dibatalkan.`,
      confirmLabel:'Hapus batch'
    });
    if(!confirmed)return;
    card.classList.add('is-deleting');
    button.disabled=true;
    button.textContent='Menghapus...';
    try{
      const response=await fetch(`/api/batches/${batchId}`,{method:'DELETE',headers:{'X-CSRF-Token':CSRF_TOKEN}});
      const data=await response.json();
      if(!response.ok)throw new Error(escapeDetail(data));
      showToast(`${batchCode} dihapus`);
      card.remove();
      if(!root.querySelector('.batch-history-item')) window.location.reload();
    }catch(error){
      card.classList.remove('is-deleting');
      button.disabled=false;
      button.textContent='Hapus';
      showToast(error.message||'Gagal menghapus batch');
    }
  }
  root.addEventListener('click',event=>{
    const button=event.target.closest('[data-delete-batch]');
    if(!button)return;
    const card=button.closest('.batch-history-item');
    if(card)removeBatch(card,button);
  });
})();
