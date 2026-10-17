(() => {
  const d = document, body = d.body;
  const drawer = d.getElementById('drawer'), overlay = d.getElementById('overlay');
  const menuBtn = d.getElementById('menu-btn'), searchBtns = d.querySelectorAll('[data-open-search]');
  const closeBtn = d.getElementById('close-btn'), q = d.getElementById('q'), list = d.getElementById('results');
  let lastFocus = null, index = null, sel = -1;

  const isOpen = () => body.classList.contains('nav-open');
  function open(focusSearch) {
    lastFocus = d.activeElement;
    drawer.inert = false;
    body.classList.add('nav-open');
    menuBtn.setAttribute('aria-expanded', 'true');
    setTimeout(() => (focusSearch ? q : closeBtn).focus(), 60);
    loadIndex();
  }
  function close() {
    body.classList.remove('nav-open');
    menuBtn.setAttribute('aria-expanded', 'false');
    drawer.inert = true;
    if (lastFocus) lastFocus.focus();
  }
  menuBtn.addEventListener('click', () => (isOpen() ? close() : open(false)));
  searchBtns.forEach(b => b.addEventListener('click', () => open(true)));
  closeBtn.addEventListener('click', close);
  overlay.addEventListener('click', close);
  d.addEventListener('keydown', e => {
    if (e.key === 'Escape' && isOpen()) { close(); return; }
    if (e.key === '/' && !isOpen() && !/input|textarea/i.test(d.activeElement.tagName)) { e.preventDefault(); open(true); return; }
    if (e.key === 'Tab' && isOpen()) {           // 引き出しの中でフォーカスを回す
      const f = drawer.querySelectorAll('a[href],button,input');
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && d.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && d.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  // 検索
  const norm = s => s.normalize('NFKC').toLowerCase().replace(/[\s・·]/g, '');
  async function loadIndex() {
    if (index) return;
    try {
      index = await (await fetch('/search.json')).json();
      index.forEach(e => { e.n = norm(e.t); e.a = norm(e.t + e.s + e.k); });
    } catch (_) { index = []; }
  }
  function render(hits, raw) {
    list.innerHTML = ''; sel = -1;
    if (!raw) return;
    if (!hits.length) {
      const li = d.createElement('li'); li.className = 'none';
      li.textContent = '見つかりませんでした。量の名前（例：電圧）や単位（例：V、J/K）で探してみてください。';
      list.appendChild(li); return;
    }
    hits.slice(0, 30).forEach(e => {
      const li = d.createElement('li'), a = d.createElement('a'), k = d.createElement('span'), s = d.createElement('span');
      a.href = e.u; k.className = 'k'; k.textContent = e.y; s.className = 's'; s.textContent = e.s;
      a.append(k, d.createTextNode(e.t), s); li.appendChild(a); list.appendChild(li);
    });
  }
  q.addEventListener('input', async () => {
    await loadIndex();
    const raw = q.value.trim(), v = norm(raw);
    if (!v) { render([], ''); return; }
    const hits = [];
    for (const e of index) {
      let score = -1;
      if (e.units && e.units.includes(raw)) score = 0;          // 単位記号がぴったり一致（大文字小文字も区別）
      else if (e.n.startsWith(v)) score = 1;
      else if (e.n.includes(v)) score = 2;
      else if (e.a.includes(v)) score = 3;
      if (score >= 0) hits.push([score + (e.y === '量' ? 0 : 0.5), e]);
    }
    hits.sort((x, y) => x[0] - y[0]);
    render(hits.map(h => h[1]), raw);
  });
  q.addEventListener('keydown', e => {
    const items = list.querySelectorAll('a');
    if (!items.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items.forEach((a, i) => a.classList.toggle('sel', i === sel));
      items[sel].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      location.href = items[Math.max(sel, 0)].href;
    }
  });

  // 練習問題：選んだらその場で答え合わせ
  d.querySelectorAll('.pq').forEach(pq => {
    pq.querySelectorAll('.ch').forEach(btn => btn.addEventListener('click', () => {
      if (pq.classList.contains('done')) return;
      pq.classList.add('done');
      const ok = btn.dataset.ok === '1';
      btn.classList.add(ok ? 'right' : 'wrong');
      pq.querySelectorAll('.ch').forEach(b => { b.disabled = true; if (b.dataset.ok === '1') b.classList.add('right'); });
      const r = d.createElement('p'); r.className = 'res ' + (ok ? 'ok' : 'ng');
      r.textContent = ok ? '正解！' : '惜しい！ 正しい組み立てを確認しましょう。';
      pq.insertBefore(r, pq.querySelector('.exp'));
      pq.querySelector('.exp').open = true;
    }));
  });

  // トップへ戻る
  const top = d.getElementById('to-top');
  const onScroll = () => top.classList.toggle('show', scrollY > 600);
  addEventListener('scroll', onScroll, { passive: true }); onScroll();
  top.addEventListener('click', () => scrollTo({ top: 0 }));
})();
