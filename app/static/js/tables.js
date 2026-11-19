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
    if (!bar) { bar = document.createElement('div'); bar.className = 'sl-pager no-print'; bar._wrap = w; w._pgBar = bar; }
    if (w.nextElementSibling !== bar) w.after(bar);
    const btn = (label, attrs, cls) => '<button type="button" class="' + (cls || '') + '" ' + attrs + '>' + label + '</button>';
    bar.innerHTML = '<span class="sl-pg-info">Showing <b>' + (from + 1) + '–' + to + '</b> of <b>' + n + '</b></span>' +
      (pages > 1 ? '<span class="sl-pg-nav">' + btn('‹ Prev', 'data-pg="' + (st.page - 1) + '"' + (st.page === 1 ? ' disabled' : '')) +
        pgNums(st.page, pages).map(x => x === '…' ? '<span class="sl-pg-gap">…</span>' : btn(x, 'data-pg="' + x + '"', x === st.page ? 'cur' : '')).join('') +
        btn('Next ›', 'data-pg="' + (st.page + 1) + '"' + (st.page === pages ? ' disabled' : '')) + '</span>' : '') +
      '<span class="sl-pg-size">Rows ' + PG_SIZES.map(z => btn(z ? z : 'All', 'data-size="' + z + '"', z === st.size ? 'cur' : '')).join('') + '</span>';
  }
  function paginate() {
    document.querySelectorAll('.workspace .content .table-wrap').forEach(w => {
      if (w.closest('.sl-modal,.mp-modal,#viewer,#tsPanel,[role=dialog]') || !w.querySelector(':scope > table') || w.querySelector(':scope > table[data-no-paginate]')) return;
      const nx = w.nextElementSibling; if (nx && nx.classList && nx.classList.contains('pager')) return;       // the server already pages this list
      if (!w._pg) w._pg = { page: 1, size: pgSaved() };
      pgDraw(w);
    });
  }
  document.addEventListener('click', e => {
    const b = e.target.closest && e.target.closest('.sl-pager button'); if (!b || b.disabled) return;
    const bar = b.closest('.sl-pager'), w = bar && bar._wrap; if (!w || !w._pg) return;
    if (b.hasAttribute('data-pg')) w._pg.page = parseInt(b.getAttribute('data-pg'), 10);
    if (b.hasAttribute('data-size')) { w._pg.size = parseInt(b.getAttribute('data-size'), 10); w._pg.page = 1; try { localStorage.setItem('sl.pagesize', String(w._pg.size)); } catch (x) {} }
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
  window.slTables={init:()=>{init();align();paginate();stickHead();fit();}};init();align();paginate();stickHead();fit();addEventListener('sl:live-updated',()=>{init();align();paginate();stickHead();fit();});document.addEventListener('DOMContentLoaded',()=>{align();paginate();stickHead();fit();});
})();
