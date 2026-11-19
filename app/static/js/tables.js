/* Semantic column widths shared by admin, teacher and parent tables. */
(() => {
  const kind=text=>{
    const t=text.replace(/\s+/g,' ').trim().toLowerCase();
    if(/^roll(?:\s*(?:no\.?|number))?$/.test(t))return 'roll';
    if(['student','student name','name','parent','second parent','teacher'].includes(t))return 'name';
    if(t.includes('email')||t==='e-mail')return 'email';
    if(t==='login')return 'login';
    if(t.includes('phone')||t.startsWith('mobile'))return 'phone';
    if(t==='children')return 'children';
    if(t==='class')return 'class';if(t==='section')return 'section';
    if(t==='status'||t==='role')return 'status';
    if(t.includes('code')||t.includes('adm.'))return 'code';
    if(['address','comment','reason','note','message'].includes(t))return 'description';
    if(t==='actions')return 'actions';return '';
  };
  function init(root=document){
    root.querySelectorAll('table.t').forEach(table=>{
      const header=table.tHead&&table.tHead.rows[0];if(!header)return;
      const columns=[];let index=0;
      Array.from(header.cells).forEach(cell=>{
        const type=cell.querySelector('input[type=checkbox]')?'check':kind(cell.textContent);
        if(type&&cell.colSpan===1){cell.classList.add('col-'+type);columns[index]=type;}
        index+=cell.colSpan;
      });
      Array.from(table.tBodies).forEach(body=>Array.from(body.rows).forEach(row=>{
        let i=0;Array.from(row.cells).forEach(cell=>{const type=columns[i];if(type&&cell.colSpan===1)cell.classList.add('col-'+type);i+=cell.colSpan;});
      }));
    });
  }
  window.slTables={init};init();addEventListener('sl:live-updated',()=>init());
})();
