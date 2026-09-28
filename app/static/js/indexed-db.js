const QueueDB=(()=>{
  const DB='kk-scanner-v1';
  const STORE='queue';

  function open(){
    return new Promise((resolve,reject)=>{
      const request=indexedDB.open(DB,1);
      request.onupgradeneeded=()=>{
        if(!request.result.objectStoreNames.contains(STORE))request.result.createObjectStore(STORE,{keyPath:'id'});
      };
      request.onsuccess=()=>resolve(request.result);
      request.onerror=()=>reject(request.error);
    });
  }

  async function write(operation){
    const db=await open();
    return new Promise((resolve,reject)=>{
      const transaction=db.transaction(STORE,'readwrite');
      try{
        operation(transaction.objectStore(STORE));
      }catch(error){
        transaction.abort();
        db.close();
        reject(error);
        return;
      }
      transaction.oncomplete=()=>{db.close();resolve();};
      transaction.onerror=()=>{db.close();reject(transaction.error);};
      transaction.onabort=()=>{db.close();reject(transaction.error);};
    });
  }

  async function read(requestFactory){
    const db=await open();
    return new Promise((resolve,reject)=>{
      const request=requestFactory(db.transaction(STORE,'readonly').objectStore(STORE));
      request.onsuccess=()=>{db.close();resolve(request.result);};
      request.onerror=()=>{db.close();reject(request.error);};
    });
  }

  return {
    put:record=>write(store=>store.put(record)),
    putMany:records=>write(store=>records.forEach(record=>store.put(record))),
    get:id=>read(store=>store.get(id)),
    all:()=>read(store=>store.getAll()),
    ids:()=>read(store=>store.getAllKeys()),
    remove:id=>write(store=>store.delete(id)),
  };
})();
