(() => {
  const form=document.querySelector('[data-record-bulk]');if(!form)return;
  const kind=form.dataset.recordKind,noun=kind==='student'?'student':'user account';
  const boxes=()=>Array.from(document.querySelectorAll('[data-record-id]:not(:disabled)'));
  function update(){
    const rows=boxes(),selected=rows.filter(box=>box.checked),all=document.querySelector('[data-record-all]');
    form.querySelector('[data-record-count]').textContent=selected.length+' selected';
    form.querySelector('[data-record-apply]').disabled=selected.length===0;
    if(all){all.disabled=rows.length===0;all.checked=rows.length>0&&selected.length===rows.length;all.indeterminate=selected.length>0&&selected.length<rows.length;}
    const action=form.querySelector('[data-record-action]').value;
    const descriptions=kind==='student'
      ? {trash:'Marks and history are kept. Section roll numbers are updated.',restore:'Students return to their section and roll numbers are updated.',purge:'Students with academic or history records cannot be permanently deleted. This cannot be undone.'}
      : {trash:'Their logins are suspended and existing sessions are signed out.',restore:'Their previous account status is restored.',purge:'Linked parent and teacher profiles are protected from permanent deletion. This cannot be undone.'};
    const prefix={trash:'Move to Trash?',restore:'Restore selected '+(kind==='student'?'students':'accounts')+'?',purge:'Delete permanently?'};
    form.dataset.confirm=selected.length+' selected '+noun+'(s). '+descriptions[action];
    form.dataset.confirmTone={trash:'warn',restore:'restore',purge:'danger'}[action];form.dataset.confirmTitle=prefix[action];
    form.dataset.confirmOk={trash:'Move to Trash',restore:'Restore',purge:'Delete permanently'}[action];
    form.dataset.confirmItems=JSON.stringify(selected.map(box=>box.dataset.recordLabel));
  }
  document.addEventListener('change',event=>{
    if(event.target.matches('[data-record-all]'))boxes().forEach(box=>box.checked=event.target.checked);
    if(event.target.matches('[data-record-all],[data-record-id],[data-record-action]'))update();
  });
  addEventListener('sl:live-updated',update);update();
})();
