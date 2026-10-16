async function j(url, opts){ const r = await fetch(url, opts); return r.json(); }

async function refresh(){
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
    refresh();
  });

  const w = await j('/api/watchlist');
  document.getElementById('watch').innerHTML = w.map(x => {
    const cls = x.sentiment > 0.1 ? 'pos' : x.sentiment < -0.1 ? 'neg' : 'neu';
    return `<div class="witem"><div><span class="s">${x.symbol}</span> <span class="p">$${x.price ? x.price.toFixed(2) : '—'}</span>
      <div style="color:#5b6378;font-size:11px">${x.headline ? '📰 ' + x.headline.slice(0,60) + '…' : ''}</div></div>
      <div style="text-align:right"><span class="sent ${cls}">${x.sentiment > 0 ? '+' : ''}${x.sentiment}</span><br>
      <button data-buy="${x.symbol}" style="width:auto;padding:6px 10px;margin-top:6px">Buy $1k</button></div></div>`;
  }).join('');
  document.querySelectorAll('[data-buy]').forEach(b => b.onclick = async () => {
    await j('/api/buy', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({symbol: b.dataset.buy, usd: 1000})});
    refresh();
  });

  const t = await j('/api/trades?limit=20');
  document.getElementById('trades').innerHTML = t.length ? t.map(x => {
    const d = new Date(x.ts*1000).toLocaleString();
    return `<div class="titem"><b>${x.side.toUpperCase()}</b> ${x.qty} ${x.symbol} @ $${x.price.toFixed(2)} · ${x.bot}<br>
      <span style="color:#5b6378">${d} — ${x.reason || ''}${x.pnl ? ' · P&L $'+x.pnl.toFixed(2) : ''}</span></div>`;
  }).join('') : '<div class="empty">No trades yet. Bots run every 15 min.</div>';
}

document.getElementById('sellAll').onclick = async () => {
  if (confirm('Sell all positions?')) { await j('/api/sell_all', {method:'POST'}); refresh(); }
};

refresh();
setInterval(refresh, 30000);
