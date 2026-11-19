/* Page selection is explicit; no unselected / hidden pages are submitted. */
(() => {
  if(!document.querySelector('[data-parent-bulk]'))return;
  const rows=()=>Array.from(document.querySelectorAll('[data-parent-id]'));
  function update(){
    const form=document.querySelector('[data-parent-bulk]');if(!form)return;            // looked up each time: the list can be swapped without a reload
    const boxes=rows(),selected=boxes.filter(box=>box.checked),all=document.querySelector('[data-parent-all]');
    form.querySelector('[data-parent-count]').textContent=selected.length+' selected';
    form.querySelector('[data-parent-apply]').disabled=selected.length===0;
    if(all){all.checked=boxes.length>0&&selected.length===boxes.length;all.indeterminate=selected.length>0&&selected.length<boxes.length;}
    const action=form.querySelector('[data-parent-action]').value;
    const settings={trash:['warn','Move selected parents to Trash?','Move to Trash'],restore:['restore','Restore selected parents?','Restore parents'],purge:['danger','Delete selected parents permanently?','Delete permanently']}[action];
    form.dataset.confirmTone=settings[0];form.dataset.confirmTitle=settings[1];form.dataset.confirmOk=settings[2];
    form.dataset.confirmItems=JSON.stringify(selected.map(box=>box.dataset.parentLabel));
    form.dataset.confirm=action==='purge'
      ? 'Delete '+selected.length+' selected parent(s) permanently? Their logins are removed and children are unlinked. Student records are kept. This cannot be undone.'
      : action==='restore' ? 'Restore '+selected.length+' selected parent(s) with their previous login status?'
      : 'Move '+selected.length+' selected parent(s) to Trash? Their logins will be suspended. Child links are kept for Restore.';
  }
  document.addEventListener('change',event=>{
    if(event.target.matches('[data-parent-all]'))rows().forEach(box=>box.checked=event.target.checked);
    if(event.target.matches('[data-parent-all],[data-parent-id],[data-parent-action]'))update();
  });
  addEventListener('sl:live-updated',update);
  update();
})();
