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
  /* Every data cell takes the text alignment of the header cell that sits above it (handles rowspan / colspan headers). */
  function align(root=document){
    root.querySelectorAll('table.t,table.tt,table.sub-matrix,table.roll-table').forEach(table=>{
      if(!table.tHead||!table.tHead.rows.length)return;
      const cols=[];let rowSpans=[];
      Array.from(table.tHead.rows).forEach(row=>{
        let c=0;const next=[];
        Array.from(row.cells).forEach(cell=>{
          while(rowSpans[c]>0){next[c]=rowSpans[c]-1;c++;}
          for(let k=0;k<cell.colSpan;k++){ if(cell.colSpan===1||!cols[c+k])cols[c+k]=cell; next[c+k]=cell.rowSpan-1; }
          c+=cell.colSpan;
        });
        rowSpans=next.map(v=>v>0?v:0);
      });
      const tag=a=>(a==='start'||a==='-webkit-left')?'left':(a==='end'||a==='-webkit-right')?'right':(a==='-webkit-center')?'center':a;
      const rows=[...Array.from(table.tBodies).flatMap(b=>Array.from(b.rows))];
      rows.forEach(row=>{
        let i=0;
        Array.from(row.cells).forEach(cell=>{
          const h=cols[i];
          if(h&&cell.tagName==='TD'&&cell.colSpan===1&&!cell.hasAttribute('data-keep-align'))cell.style.textAlign=tag(getComputedStyle(h).textAlign);
          i+=cell.colSpan;
        });
      });
    });
  }
  window.slTables={init:()=>{init();align();}};init();align();addEventListener('sl:live-updated',()=>{init();align();});document.addEventListener('DOMContentLoaded',()=>align());
})();
