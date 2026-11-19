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
  /* Long tables that are not already paged by the server: show a page at a time, entirely in the browser.
     Every row stays in the page (so a marks form still saves all pages) - only the display changes. No reload, no request. */
  const PG_SIZES = [10, 25, 50, 100, 0], PG_MIN = 25;
  const pgSaved = () => { try { const v = parseInt(localStorage.getItem('sl.pagesize'), 10); return PG_SIZES.includes(v) ? v : 25; } catch (e) { return 25; } };
  const pgRows = w => { const t = w.querySelector(':scope > table'); return t && t.tBodies[0] ? Array.from(t.tBodies[0].rows).filter(r => r.cells.length > 1 || (r.cells[0] && r.cells[0].colSpan < 2)) : []; };
  function pgNums(page, pages) {
    const keep = new Set([1, pages, page - 1, page, page + 1]); const out = []; let last = 0;
    for (let n = 1; n <= pages; n++) if (keep.has(n)) { if (n - last > 1) out.push('…'); out.push(n); last = n; }
    return out;
  }
  function pgDraw(w) {
    const st = w._pg, rows = pgRows(w), n = rows.length;
    let bar = w._pgBar; if (bar && !bar.isConnected) bar = w._pgBar = null;
    if (n <= PG_MIN) { rows.forEach(r => r.classList.remove('pg-hide')); if (bar) bar.remove(), w._pgBar = null; return; }
    const size = st.size || n, pages = Math.max(1, Math.ceil(n / size));
    st.page = Math.min(Math.max(1, st.page), pages);
    const from = (st.page - 1) * size, to = Math.min(n, from + size);
    rows.forEach((r, i) => r.classList.toggle('pg-hide', !(i >= from && i < to)));
    if (!bar) {                                                              // one bar per table: counter | page numbers | rows per page
      bar = document.createElement('div'); bar.className = 'sl-pager no-print'; bar._wrap = w; w._pgBar = bar;
      bar.innerHTML = '<span class="sl-pg-info"></span><span class="sl-pg-nav"></span><label class="sl-pg-size"><span>Rows per page</span><select aria-label="Rows per page">' +
        PG_SIZES.map(z => '<option value="' + z + '">' + (z || 'All') + '</option>').join('') + '</select></label>';
    }
    if (w.nextElementSibling !== bar) w.after(bar);
    const btn = (label, attrs, cls) => '<button type="button" class="' + (cls || '') + '" ' + attrs + '>' + label + '</button>';
    bar.querySelector('.sl-pg-info').innerHTML = 'Showing <b>' + (from + 1) + '–' + to + '</b> of <b>' + n + '</b>';
    bar.querySelector('.sl-pg-nav').innerHTML = pages > 1 ? btn('‹ Prev', 'data-pg="' + (st.page - 1) + '"' + (st.page === 1 ? ' disabled' : '')) +
      pgNums(st.page, pages).map(x => x === '…' ? '<span class="sl-pg-gap">…</span>' : btn(x, 'data-pg="' + x + '"', x === st.page ? 'cur' : '')).join('') +
      btn('Next ›', 'data-pg="' + (st.page + 1) + '"' + (st.page === pages ? ' disabled' : '')) : '';
    const sel = bar.querySelector('select'); if (sel.value !== String(st.size)) { sel.value = String(st.size); sel.dispatchEvent(new Event('input', { bubbles: false })); }
    if (window.slPretty) slPretty.refresh();
  }
  function paginate() {
    document.querySelectorAll('.workspace .content .table-wrap').forEach(w => {
      if (w.closest('.sl-modal,.mp-modal,#viewer,#tsPanel,[role=dialog]') || !w.querySelector(':scope > table') || w.querySelector(':scope > table[data-no-paginate]')) return;
      const nx = w.nextElementSibling, serverPaged = (nx && nx.classList && nx.classList.contains('pager')) || (w.parentElement && w.parentElement.querySelector(':scope > .pager'));
      if (serverPaged) { if (w._pgBar) { w._pgBar.remove(); w._pgBar = null; } w.querySelectorAll('.pg-hide').forEach(r => r.classList.remove('pg-hide')); return; }   // the server already pages this list
      if (!w._pg) w._pg = { page: 1, size: pgSaved() };
      pgDraw(w);
    });
    document.querySelectorAll('.sl-pager').forEach(bar => {                    // drop bars whose table is gone / replaced, and any duplicate
      if (!bar._wrap || !bar._wrap.isConnected || bar._wrap._pgBar !== bar || bar.previousElementSibling !== bar._wrap) bar.remove();
    });
  }
  document.addEventListener('change', e => {
    const sel = e.target.closest && e.target.closest('.sl-pager select'); if (!sel) return;
    const w = sel.closest('.sl-pager')._wrap; if (!w || !w._pg) return;
    w._pg.size = parseInt(sel.value, 10); w._pg.page = 1;
    try { localStorage.setItem('sl.pagesize', String(w._pg.size)); } catch (x) {}
    pgDraw(w); w.scrollTop = 0; fit();
  });
  document.addEventListener('click', e => {
    const b = e.target.closest && e.target.closest('.sl-pager button'); if (!b || b.disabled) return;
    const bar = b.closest('.sl-pager'), w = bar && bar._wrap; if (!w || !w._pg) return;
    if (b.hasAttribute('data-pg')) w._pg.page = parseInt(b.getAttribute('data-pg'), 10);
    pgDraw(w); w.scrollTop = 0; fit();
  });

  /* Second header row sticks right below the first one. */
  function stickHead(){
    document.querySelectorAll('table.marks-grid').forEach(t=>{const r=t.tHead&&t.tHead.rows[0];if(r)t.style.setProperty('--hr1',r.getBoundingClientRect().height+'px');});
  }
  /* Other table boxes: as tall as the screen allows from where they start, so their own scrollbars stay on screen. */
  function fit(){
    document.querySelectorAll('.workspace .content .table-wrap').forEach(w=>{
      if(w.querySelector('.marks-grid')||w.closest('.modal,.pv-box,[role=dialog]')||!w.querySelector('table'))return;
      w.style.maxHeight='';
      const top=w.getBoundingClientRect().top+window.scrollY;
      const nxs=w.nextElementSibling,pager=nxs&&nxs.classList&&(nxs.classList.contains('pager')||nxs.classList.contains('sl-pager'))?72:0;
      w.style.maxHeight=Math.max(280,window.innerHeight-top-26-pager)+'px';
    });
  }
  addEventListener('resize',()=>{stickHead();fit();});addEventListener('load',()=>{stickHead();fit();});
  window.slTables={init:()=>{labelActions();init();narrow();align();paginate();stickHead();fit();}};labelActions();init();narrow();align();paginate();stickHead();fit();addEventListener('sl:live-updated',()=>{labelActions();init();narrow();align();paginate();stickHead();fit();});document.addEventListener('DOMContentLoaded',()=>{labelActions();narrow();align();paginate();stickHead();fit();});
})();
