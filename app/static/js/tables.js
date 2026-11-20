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
    if(t==='actions')return 'actions';
    if(t==='#'||t==='no'||t==='no.'||t==='sl'||t==='sl.'||t==='sl no'||t==='sr no'||t==='s.no')return 'index';return '';
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
  /* A header cell with no text above a column of Edit / Delete / Restore buttons is the actions column: name it. */
  function labelActions(root=document){
    root.querySelectorAll('table.t').forEach(table=>{
      if(table.classList.contains('marks-grid')||table.hasAttribute('data-no-actions-label')||!table.tHead||table.tHead.rows.length!==1||!table.tBodies[0])return;
      const heads=Array.from(table.tHead.rows[0].cells),rows=Array.from(table.tBodies[0].rows).filter(r=>r.cells.length===heads.length);
      if(!rows.length)return;
      heads.forEach((th,i)=>{
        if(th.colSpan>1||th.textContent.replace(/\s+/g,'').length||th.querySelector('input,svg,img'))return;
        const withControls=rows.filter(r=>r.cells[i].querySelector('.btn,button,a[href],form')).length;
        if(withControls&&withControls>=rows.length*0.5){th.textContent='Actions';th.classList.add('col-actions');rows.forEach(r=>r.cells[i].classList.add('col-actions'));}
      });
    });
  }
  /* Columns that only hold short numbers (#, counts, ids) shrink to fit instead of taking a full share of the width. */
  const NUM_HEAD=/^(#|no\.?|sl\.?(\s*no\.?)?|sr\.?(\s*no\.?)?|s\.?\s*no\.?|id|order|sort|count|total|students?|sections?|classes|subjects?|teachers?|max|rank|age|year|%|days|sessions)$/i;
  const NUM_CELL=/^[\d.,\-–\/%\s]{1,9}$/;
  function narrow(root=document){
    root.querySelectorAll('table.t').forEach(table=>{
      if(table.classList.contains('marks-grid')||table.hasAttribute('data-no-narrow')||!table.tHead||table.tHead.rows.length!==1||!table.tBodies[0])return;
      const heads=Array.from(table.tHead.rows[0].cells),rows=Array.from(table.tBodies[0].rows).slice(0,80).filter(r=>r.cells.length===heads.length);
      if(!rows.length)return;
      heads.forEach((th,i)=>{
        if(th.colSpan>1||th.querySelector('input'))return;
        const name=th.textContent.replace(/\s+/g,' ').trim(),texts=rows.map(r=>r.cells[i].textContent.replace(/\s+/g,' ').trim()).filter(Boolean);
        const numeric=texts.length&&texts.every(x=>NUM_CELL.test(x)),yes=(name==='#'||NUM_HEAD.test(name))&&(numeric||name==='#');
        const on=!!yes&&name.length<=14;
        th.classList.toggle('col-narrow',on);th.classList.toggle('col-index',on&&name==='#');
        rows.forEach(r=>r.cells[i].classList.toggle('col-narrow',on));
      });
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
  /* Long tables that the server does not page: ten rows at a time, entirely in the browser.
     Every row stays in the page (a marks form still saves all pages) - only the display changes. No reload, no request. */
  const PG_SIZE = 10;
  const pgRows = w => { const t = w.querySelector(':scope > table'); return t && t.tBodies[0] ? Array.from(t.tBodies[0].rows).filter(r => r.cells.length > 1 || (r.cells[0] && r.cells[0].colSpan < 2)) : []; };
  function pgNums(page, pages) {
    const keep = new Set([1, pages, page - 1, page, page + 1]); const out = []; let last = 0;
    for (let n = 1; n <= pages; n++) if (keep.has(n)) { if (n - last > 1) out.push('…'); out.push(n); last = n; }
    return out;
  }
  function pgDraw(w) {
    const st = w._pg, rows = pgRows(w), n = rows.length;
    let bar = w._pgBar; if (bar && !bar.isConnected) bar = w._pgBar = null;
    if (n <= PG_SIZE) { rows.forEach(r => r.classList.remove('pg-hide')); w.classList.toggle('is-paged', n >= PG_SIZE); if (bar) bar.remove(), w._pgBar = null; return; }   // a full page (10 rows) gets the same height as the longer lists
    const pages = Math.ceil(n / PG_SIZE);
    st.page = Math.min(Math.max(1, st.page), pages);
    const from = (st.page - 1) * PG_SIZE, to = Math.min(n, from + PG_SIZE);
    rows.forEach((r, i) => r.classList.toggle('pg-hide', !(i >= from && i < to)));
    w.classList.add('is-paged');
    if (!bar) { bar = document.createElement('div'); bar.className = 'sl-pager no-print'; bar.setAttribute('data-client', '1'); bar._wrap = w; w._pgBar = bar; bar.innerHTML = '<span class="sl-pg-info"></span><span class="sl-pg-nav"></span>'; }
    if (w.nextElementSibling !== bar) w.after(bar);
    const btn = (label, attrs, cls) => '<button type="button" class="' + (cls || '') + '" ' + attrs + '>' + label + '</button>';
    bar.querySelector('.sl-pg-info').innerHTML = 'Showing <b>' + (from + 1) + '–' + to + '</b> of <b>' + n + '</b>';
    bar.querySelector('.sl-pg-nav').innerHTML = btn('‹ Prev', 'data-pg="' + (st.page - 1) + '"' + (st.page === 1 ? ' disabled' : '')) +
      pgNums(st.page, pages).map(x => x === '…' ? '<span class="sl-pg-gap">…</span>' : btn(x, 'data-pg="' + x + '"', x === st.page ? 'cur' : '')).join('') +
      btn('Next ›', 'data-pg="' + (st.page + 1) + '"' + (st.page === pages ? ' disabled' : ''));
  }
  function paginate() {
    document.querySelectorAll('.workspace .content .table-wrap').forEach(w => {
      if (w.closest('.sl-modal,.mp-modal,#viewer,#tsPanel,[role=dialog]') || !w.querySelector(':scope > table') || w.querySelector(':scope > table[data-no-paginate]')) return;
      const nx = w.nextElementSibling, isServer = e => e && e.classList && e.classList.contains('sl-pager') && !e.hasAttribute('data-client');
      const serverPaged = isServer(nx) || (w.parentElement && Array.from(w.parentElement.children).some(isServer));
      if (serverPaged) {                                                         // the server already pages this list: same height as every other paged table
        if (w._pgBar) { w._pgBar.remove(); w._pgBar = null; }
        w.querySelectorAll('.pg-hide').forEach(r => r.classList.remove('pg-hide')); w.classList.add('is-paged'); return;
      }
      if (!w._pg) w._pg = { page: 1 };
      pgDraw(w);
    });
    document.querySelectorAll('.sl-pager[data-client]').forEach(bar => {         // drop bars whose table is gone / replaced, and any duplicate
      if (!bar._wrap || !bar._wrap.isConnected || bar._wrap._pgBar !== bar || bar.previousElementSibling !== bar._wrap) bar.remove();
    });
  }
  document.addEventListener('click', e => {
    const b = e.target.closest && e.target.closest('.sl-pager[data-client] button'); if (!b || b.disabled) return;
    const bar = b.closest('.sl-pager'), w = bar && bar._wrap; if (!w || !w._pg) return;
    if (b.hasAttribute('data-pg')) w._pg.page = parseInt(b.getAttribute('data-pg'), 10);
    pgDraw(w); w.scrollTop = 0;
  });

  /* Second header row sticks right below the first one. */
  function stickHead(){
    document.querySelectorAll('table.marks-grid').forEach(t=>{const r=t.tHead&&t.tHead.rows[0];if(r)t.style.setProperty('--hr1',r.getBoundingClientRect().height+'px');});
  }
  function fit(){ document.querySelectorAll('.workspace .content .table-wrap').forEach(w=>{ if(w.style.maxHeight) w.style.maxHeight=''; }); }   /* height is set in CSS (--table-h) */
  addEventListener('resize',()=>{stickHead();fit();});addEventListener('load',()=>{stickHead();fit();});
  window.slTables={init:()=>{labelActions();init();narrow();align();paginate();stickHead();fit();}};labelActions();init();narrow();align();paginate();stickHead();fit();addEventListener('sl:live-updated',()=>{labelActions();init();narrow();align();paginate();stickHead();fit();});document.addEventListener('DOMContentLoaded',()=>{labelActions();narrow();align();paginate();stickHead();fit();});
})();
