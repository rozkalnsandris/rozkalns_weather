/* Local design prototype navigation only; never sends provider or personal data. */
(()=>{
 const routes={overview:['Overview','weather-design-system-v2','◉'],models:['Models','weather-models-v1','▥'],radar:['Radar','weather-radar-v1','◎'],accuracy:['Accuracy','weather-accuracy-v1','▤'],status:['Status','weather-status-v1','⚙']};
 const query=new URLSearchParams(location.search),theme=query.get('theme')==='dark'?'dark':'light';
 const nav=document.querySelector('nav');if(!nav)return;
 const current=Object.keys(routes).find(key=>location.pathname.includes('/'+routes[key][1]+'/'));
 nav.setAttribute('aria-label','Maketu navigācija');
 nav.innerHTML=Object.entries(routes).map(([key,[label,folder,icon]])=>'<a data-route="'+key+'" '+(key===current?'aria-current="page" ':'')+'href="../'+folder+'/preview.html?theme='+theme+'">'+'<span class="nav-icon" aria-hidden="true">'+icon+'</span><span>'+label+'</span>'+'</a>').join('');
 const style=document.createElement('style');style.textContent='nav a>span{display:block;flex:none;padding:0;background:transparent;border-radius:0;color:inherit;font-size:10px}nav .nav-icon{display:block;font-size:20px;line-height:24px}nav a{flex:1;text-align:center;padding:10px 2px;font-size:10px;color:var(--muted);text-decoration:none;min-height:48px}nav a[aria-current=page]{background:var(--soft);color:var(--accent);border-radius:9px}';document.head.append(style);
 nav.querySelectorAll('[data-route]').forEach(a=>a.addEventListener('click',event=>{if(query.get('shell')==='1'&&parent!==window){event.preventDefault();parent.postMessage({type:'weather-design-navigate',page:a.dataset.route},'*')}}));
})();
