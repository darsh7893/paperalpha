async function j(url, opts){
  const r = await fetch(url, opts);
  if (r.status === 401) throw new Error('auth');
  const d = await r.json();
  if (!r.ok) throw new Error(d.detail || 'error');
  return d;
}

let mode = 'login';
const authEl = document.getElementById('auth');
const appEl = document.getElementById('app');

function setMode(m){
  mode = m;
  document.getElementById('tabLogin').classList.toggle('active', m === 'login');
  document.getElementById('tabRegister').classList.toggle('active', m === 'register');
  document.getElementById('authGo').textContent = m === 'login' ? 'Log in' : 'Sign up';
}
document.getElementById('tabLogin').onclick = () => setMode('login');
document.getElementById('tabRegister').onclick = () => setMode('register');

document.getElementById('authGo').onclick = async () => {
  const u = document.getElementById('username').value;
  const p = document.getElementById('password').value;
  const err = document.getElementById('authErr');
  err.textContent = '';
  try {
    await j('/api/' + mode, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: u, password: p})});
    boot();
  } catch (e) { err.textContent = e.message; }
};

async function refreshStatus(){
  try {
    const s = await j('/api/status');
    document.getElementById('equity').textContent = '$' + s.equity.toLocaleString();
    const pnl = document.getElementById('pnl');
    pnl.textContent = (s.pnl >= 0 ? '+' : '') + '$' + s.pnl.toLocaleString() + ` (${s.pnl_pct}%)`;
    pnl.className = 'pnl ' + (s.pnl >= 0 ? 'up' : 'down');
    document.getElementById('cash').textContent = '$' + s.cash.toLocaleString();

    const bots = document.getElementById('bots');
    const tot = Object.values(s.weights).reduce((a,b)=>a+b,0) || 1;
    bots.innerHTML = Object.entries(s.bot_stats).map(([name, st]) => {
      const w = s.weights[name] || 0;
      const wr = st.trades ? Math.round(st.wins/st.trades*100) : 0;
      return `<div class="bot"><div class="name">${name} bot</div>
        <div class="meta">${st.trades} trades · ${wr}% win · P&L $${Math.round(st.total_pnl).toLocaleString()}</div>
        <div class="bar"><i style="width:${Math.round(w/tot*100)}%"></i></div></div>`;
    }).join('');

    const pos = document.getElementById('positions');
    pos.innerHTML = s.positions.length ? s.positions.map(p =>
      `<div class="pos"><div><b>${p.symbol}</b><br><span style="color:#8b93a7">${p.qty} @ $${p.avg_price.toFixed(2)}</span></div>
       <div style="text-align:right">$${p.value.toLocaleString()}<br><button data-sell="${p.symbol}" style="width:auto;padding:6px 10px;margin:4px 0 0">Sell</button></div></div>`
    ).join('') : '<div class="empty">No open positions yet.</div>';
    pos.querySelectorAll('[data-sell]').forEach(b => b.onclick = async () => {
      await j('/api/sell', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({symbol: b.dataset.sell})});
      refreshStatus();
    });
  } catch(e) { /* keep old values; retry next cycle */ }
}

function drawChart(cv, data, color){
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  if (!w || !h || !data || data.length < 2) return;
  cv.width = w * dpr; cv.height = h * dpr;
  const ctx = cv.getContext('2d');
  ctx.scale(dpr, dpr);
  const min = Math.min(...data), max = Math.max(...data);
  const span = (max - min) || 1;
  const X = i => 2 + i * (w - 4) / (data.length - 1);
  const Y = v => 3 + (h - 6) * (1 - (v - min) / span);
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, color + '44'); g.addColorStop(1, color + '00');
  ctx.beginPath(); ctx.moveTo(X(0), Y(data[0]));
  data.forEach((v, i) => ctx.lineTo(X(i), Y(v)));
  ctx.lineTo(X(data.length - 1), h); ctx.lineTo(X(0), h); ctx.closePath();
  ctx.fillStyle = g; ctx.fill();
  ctx.beginPath(); ctx.moveTo(X(0), Y(data[0]));
  data.forEach((v, i) => ctx.lineTo(X(i), Y(v)));
  ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke();
  ctx.beginPath(); ctx.arc(X(data.length - 1), Y(data[data.length - 1]), 2.5, 0, 7);
  ctx.fillStyle = color; ctx.fill();
}

function sentClass(v){ return v > 0.1 ? 'pos' : v < -0.1 ? 'neg' : 'neu'; }

async function refreshWatch(){
  const el = document.getElementById('watch');
  try {
    const w = await j('/api/watchlist');
    el.innerHTML = w.map(x => {
      const cls = sentClass(x.sentiment);
      const up = x.spark && x.spark.length > 1 && x.spark[x.spark.length-1] >= x.spark[0];
      const buyBtn = x.price
        ? `<button data-buy="${x.symbol}" style="width:auto;padding:6px 10px;margin-top:6px">Buy $1k</button>`
        : `<div style="color:#5b6378;font-size:11px;margin-top:6px">price unavailable</div>`;
      return `<div class="witem" data-sym="${x.symbol}">
        <div class="wrow">
          <div style="flex:1;min-width:0"><span class="s">${x.symbol}</span>
            <span class="p" data-px="${x.price || 0}">$${x.price ? x.price.toFixed(2) : '—'}</span>
            <div style="color:#5b6378;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${x.headline ? '📰 ' + x.headline.slice(0,55) + '…' : ''}</div>
          </div>
          <canvas class="spark" data-spark='${JSON.stringify(x.spark || [])}' data-up="${up ? 1 : 0}"></canvas>
          <div style="text-align:right"><span class="sent ${cls}">${x.sentiment > 0 ? '+' : ''}${x.sentiment}</span><br>${buyBtn}</div>
        </div>
        <div class="wdetail" hidden></div>
      </div>`;
    }).join('');
    el.querySelectorAll('canvas.spark').forEach(cv => {
      drawChart(cv, JSON.parse(cv.dataset.spark), cv.dataset.up === '1' ? '#22c55e' : '#ef4444');
    });
    el.querySelectorAll('[data-buy]').forEach(b => b.onclick = async (e) => {
      e.stopPropagation();
      const r = await j('/api/buy', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({symbol: b.dataset.buy, usd: 1000})});
      if (!r.ok) alert(r.error || 'buy failed');
      refreshStatus();
    });
    el.querySelectorAll('.witem .wrow').forEach(row => {
      row.onclick = () => toggleDetail(row.closest('.witem'));
    });
  } catch(e) {
    el.innerHTML = '<div class="empty">Market data is loading slowly — retrying…</div>';
  }
}

async function toggleDetail(item){
  const det = item.querySelector('.wdetail');
  const sym = item.dataset.sym;
  if (!det.hidden) { det.hidden = true; return; }
  el_qsa('.wdetail').forEach(d => { if (d !== det) d.hidden = true; });
  det.hidden = false;
  if (!det.dataset.loaded){
    det.innerHTML = '<div class="empty">Loading chart…</div>';
    try {
      const c = await j('/api/chart?symbol=' + sym);
      const up = c.change_pct >= 0;
      const color = up ? '#22c55e' : '#ef4444';
      const rsiCls = c.rsi >= 70 ? 'neg' : c.rsi <= 30 ? 'pos' : 'neu';
      const trend = c.vs_sma20_pct >= 0 ? '▲ above' : '▼ below';
      det.innerHTML = `
        <div class="dhead"><b>$${c.price.toFixed(2)}</b>
          <span class="${up ? 'pos' : 'neg'}">${up ? '+' : ''}${c.change_pct}% today</span></div>
        <canvas class="bigchart"></canvas>
        <div class="statgrid">
          <div class="stat"><span>90d high</span><b>$${c.high_90.toFixed(2)}</b></div>
          <div class="stat"><span>90d low</span><b>$${c.low_90.toFixed(2)}</b></div>
          <div class="stat"><span>vs 20-day avg</span><b>${trend} ${Math.abs(c.vs_sma20_pct)}%</b></div>
          <div class="stat"><span>RSI (14)</span><b class="${rsiCls}">${c.rsi}</b></div>
          <div class="stat"><span>news mood</span><b class="${sentClass(c.sentiment)}">${c.sentiment > 0 ? '+' : ''}${c.sentiment}</b></div>
          <div class="stat"><span>bot read</span><b>${c.vs_sma20_pct >= 0 && c.sentiment > -0.1 ? 'bullish' : c.vs_sma20_pct < 0 && c.sentiment < 0.1 ? 'bearish' : 'mixed'}</b></div>
        </div>
        ${c.headline ? `<div style="color:#5b6378;font-size:12px;margin-top:8px">📰 ${c.headline}</div>` : ''}`;
      const cv = det.querySelector('.bigchart');
      drawChart(cv, c.closes, color);
      det.dataset.loaded = '1';
    } catch(e) {
      det.innerHTML = '<div class="empty">Chart unavailable right now.</div>';
    }
  }
}
function el_qsa(s){ return document.querySelectorAll(s); }

async function tickPrices(){
  // live ticker: refresh prices in place every 20s (server cache is 60s)
  try {
    const p = await j('/api/prices');
    document.querySelectorAll('#watch .witem').forEach(item => {
      const px = p[item.dataset.sym];
      if (px == null) return;
      const elx = item.querySelector('.p');
      const old = parseFloat(elx.dataset.px || '0');
      elx.textContent = '$' + px.toFixed(2);
      elx.dataset.px = px;
      elx.classList.remove('up', 'dn');
      if (old && px > old) { elx.classList.add('up'); }
      else if (old && px < old) { elx.classList.add('dn'); }
    });
    const tt = document.getElementById('tickTime');
    if (tt) tt.textContent = 'live · ' + new Date().toLocaleTimeString();
  } catch(e) {}
}

async function refreshTrades(){
  try {
    const t = await j('/api/trades?limit=20');
    document.getElementById('trades').innerHTML = t.length ? t.map(x => {
      const d = new Date(x.ts*1000).toLocaleString();
      return `<div class="titem"><b>${x.side.toUpperCase()}</b> ${x.qty} ${x.symbol} @ $${x.price.toFixed(2)} · ${x.bot}<br>
        <span style="color:#5b6378">${d} — ${x.reason || ''}${x.pnl ? ' · P&L $'+x.pnl.toFixed(2) : ''}</span></div>`;
    }).join('') : '<div class="empty">No trades yet. Bots run every 15 min.</div>';
  } catch(e) {}
}

async function refreshSettings(){
  try {
    const set = await j('/api/settings');
    const bt = document.getElementById('botToggle');
    bt.textContent = set.bot_enabled ? 'ON' : 'OFF';
    bt.classList.toggle('on', set.bot_enabled);
    bt.onclick = async () => {
      const r = await j('/api/settings', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({bot_enabled: !set.bot_enabled})});
      bt.textContent = r.bot_enabled ? 'ON' : 'OFF';
      bt.classList.toggle('on', r.bot_enabled);
    };
  } catch(e) {}
}

function refresh(){
  // independent: one slow section can never block the others
  refreshStatus();
  refreshWatch();
  refreshTrades();
  refreshSettings();
}

async function boot(){
  try {
    const me = await j('/api/me');
    document.getElementById('who').textContent = '· ' + me.username + (me.is_admin ? ' (admin)' : '');
    authEl.style.display = 'none';
    appEl.style.display = 'block';
    document.getElementById('sellAll').onclick = async () => {
      if (confirm('Sell all positions?')) { await j('/api/sell_all', {method:'POST'}); refresh(); }
    };
    document.getElementById('logout').onclick = async () => {
      await j('/api/logout', {method: 'POST'});
      location.reload();
    };
    refresh();
    setInterval(refresh, 30000);
    setInterval(tickPrices, 20000);  // live price ticker
    tickPrices();
  } catch (e) {
    authEl.style.display = 'block';
    appEl.style.display = 'none';
  }
}

boot();
