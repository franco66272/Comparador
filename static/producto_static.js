(() => {
  const qs = new URLSearchParams(location.search), codigo = qs.get('codigo');
  const $ = id => document.getElementById(id);
  const money = n => '$' + Math.round(Number(n) || 0).toLocaleString('es-AR');
  const safe = v => String(v ?? '').trim();
  const esc = v => safe(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const shortDate = s => { const d=new Date(String(s||'').replace(' ','T')); return Number.isNaN(d.getTime())?String(s||'').slice(0,10):d.toLocaleDateString('es-AR',{day:'numeric',month:'short'}).replace('.',''); };
  const nameStore = key => safe(key).replace(/_com_ar$|_com$|_ar$/,'').replace(/[_-]+/g,' ').replace(/\b\w/g,x=>x.toUpperCase());

  function drawChart(serie){
    if(!serie.length)return;
    $('historyEmpty').hidden=true; $('historyContent').hidden=false;
    const svg=$('graficoPrecio'),line=$('lineaPrecio'),area=$('priceArea'),dots=$('puntosPrecio'),grid=$('chartGrid'),axes=$('chartAxes'),tooltip=$('priceTooltip'),stage=$('priceChartStage');
    const W=900,H=330,left=68,right=24,top=22,bottom=42,plotW=W-left-right,plotH=H-top-bottom;
    const values=serie.map(x=>Number(x.precio)).filter(Number.isFinite); let mn=Math.min(...values),mx=Math.max(...values);
    if(mn===mx){const pad=Math.max(1,mn*.05);mn=Math.max(0,mn-pad);mx+=pad;}else{const pad=(mx-mn)*.08;mn=Math.max(0,mn-pad);mx+=pad;}
    const X=i=>left+(serie.length===1?plotW/2:i*(plotW/(serie.length-1))),Y=v=>top+((mx-v)/(mx-mn))*plotH;
    const smooth=pts=>{if(pts.length===1)return`M ${pts[0][0]} ${pts[0][1]}`;let d=`M ${pts[0][0]} ${pts[0][1]}`;for(let i=1;i<pts.length;i++){const a=pts[i-1],b=pts[i],c=(a[0]+b[0])/2;d+=` C ${c} ${a[1]}, ${c} ${b[1]}, ${b[0]} ${b[1]}`;}return d;};
    for(let i=0;i<5;i++){const val=mn+(mx-mn)*(i/4),y=Y(val),l=document.createElementNS('http://www.w3.org/2000/svg','line');l.setAttribute('x1',left);l.setAttribute('x2',W-right);l.setAttribute('y1',y);l.setAttribute('y2',y);l.setAttribute('class','price-chart-grid');grid.appendChild(l);const t=document.createElementNS('http://www.w3.org/2000/svg','text');t.setAttribute('x',left-10);t.setAttribute('y',y+4);t.setAttribute('text-anchor','end');t.setAttribute('class','price-chart-axis');t.textContent=money(val);axes.appendChild(t);}
    const every=Math.max(1,Math.ceil(serie.length/6));serie.forEach((x,i)=>{if(i%every!==0&&i!==serie.length-1)return;const t=document.createElementNS('http://www.w3.org/2000/svg','text');t.setAttribute('x',X(i));t.setAttribute('y',H-12);t.setAttribute('text-anchor','middle');t.setAttribute('class','price-chart-axis');t.textContent=shortDate(x.fecha);axes.appendChild(t);});
    const pts=serie.map((x,i)=>[X(i),Y(Number(x.precio))]),d=smooth(pts);line.setAttribute('d',d);area.setAttribute('d',`${d} L ${pts[pts.length-1][0]} ${H-bottom} L ${pts[0][0]} ${H-bottom} Z`);
    serie.forEach((x,i)=>{const c=document.createElementNS('http://www.w3.org/2000/svg','circle');c.setAttribute('cx',X(i));c.setAttribute('cy',Y(Number(x.precio)));c.setAttribute('r',serie.length<12?'5':'3.5');c.setAttribute('class','price-chart-dot');c.addEventListener('mouseenter',()=>{const r=svg.getBoundingClientRect(),sr=stage.getBoundingClientRect(),sx=r.width/W,sy=r.height/H;tooltip.hidden=false;tooltip.querySelector('.price-chart-tooltip-date').textContent=shortDate(x.fecha);tooltip.querySelector('.price-chart-tooltip-price').textContent=money(x.precio);tooltip.style.left=(X(i)*sx+r.left-sr.left)+'px';tooltip.style.top=(Y(Number(x.precio))*sy+r.top-sr.top)+'px';});c.addEventListener('mouseleave',()=>tooltip.hidden=true);dots.appendChild(c);});
    $('chartCurrent').textContent=money(serie[serie.length-1].precio);$('historyRows').innerHTML='<div class="history-header"><span>Fecha</span><span>Precio</span><span>Fuente</span></div>'+serie.slice().reverse().map(x=>`<div class="history-row"><span>${esc(String(x.fecha||'').replace('T',' '))}</span><strong>${money(x.precio)}</strong><span>${esc(x.fuente||'automático')}</span></div>`).join('');
  }

  async function init(){
    if(!codigo){$('productName').textContent='Producto no encontrado';return;}
    const productPromise=fetch(`data/productos/${encodeURIComponent(codigo)}.json`,{cache:'no-cache'}).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();});
    const metaPromise=fetch('data/catalogo_meta.json',{cache:'no-cache'}).then(r=>r.ok?r.json():null).catch(()=>null);
    try{
      const [data,meta]=await Promise.all([productPromise,metaPromise]);
      if(meta&&Array.isArray(meta.categorias)){
        const panel=$('categoryPanel');
        for(const c of meta.categorias){const a=document.createElement('a');a.className='category-item';a.href=`https://tecnoradar.onrender.com/?categoria=${encodeURIComponent(c.nombre)}`;a.innerHTML=`<span>${esc(c.nombre)}</span><small>${Number(c.productos||0).toLocaleString('es-AR')}</small>`;panel.appendChild(a);}
      }
      const p=data.producto||{},d=data.detalle||{},h=Array.isArray(data.historial)?data.historial:[],tienda=safe(p.tienda),tiendaNombre=safe(p.tienda_nombre)||nameStore(tienda);
      document.title='TecnoRadar - '+safe(p.nombre);$('productName').textContent=safe(p.nombre)||'Producto';$('storeName').textContent=tiendaNombre;$('storeNav').textContent=tiendaNombre;$('storeCrumb').textContent=tiendaNombre;
      $('storeLink').href=`https://tecnoradar.onrender.com/?tienda=${encodeURIComponent(tienda)}`;$('storeNav').href=`https://tecnoradar.onrender.com/?tienda=${encodeURIComponent(tienda)}`;$('storeCrumb').href=`https://tecnoradar.onrender.com/?tienda=${encodeURIComponent(tienda)}`;$('officialLink').href=safe(p.url)||'#';$('verifyLink').href=`https://tecnoradar.onrender.com/producto/${encodeURIComponent(codigo)}?verificar=1`;
      const img=safe(d.imagen)||safe(p.imagen);$('detailMedia').innerHTML=img?`<img src="${esc(img)}" alt="${esc(p.nombre)}" referrerpolicy="no-referrer">`:'<div class="sin-imagen">Sin imagen</div>';$('priceCurrent').textContent=money(p.precio);
      if(p.precio_anterior&&Number(p.precio_anterior)>Number(p.precio)){const pct=Math.round((1-Number(p.precio)/Number(p.precio_anterior))*100);$('discount').hidden=false;$('discount').textContent='-'+pct+'%';}
      const stock=Number(p.stock);$('stockLabel').textContent=stock>0?'En stock':'Sin stock';$('stockLabel').classList.toggle('ok',stock>0);$('verifiedLabel').textContent=p.actualizado_en?('Actualizado: '+String(p.actualizado_en).replace('T',' ').slice(0,16)):'Actualización automática';$('description').textContent=safe(d.descripcion)||'La descripción detallada se incorporará cuando esté disponible en la fuente oficial.';$('historyCount').textContent=h.length+' registro'+(h.length===1?'':'s');if(h.length)drawChart(h);
    }catch(err){$('productName').textContent='No se pudo cargar el producto';$('description').textContent='Intentá nuevamente en unos segundos.';console.error(err);}
  }
  init();
})();
