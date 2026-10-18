const CACHE='sepandyar-v2';
const CORE=['/','/index.html','/manifest.webmanifest'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(CORE)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 // داده‌های API هرگز کش نمی‌شوند: دارو، سلامت، کیف پول و هشدارها باید همیشه تازه باشند.
 // با respondWith نکردن، درخواست مستقیم به شبکه می‌رود.
 if(event.request.method!=='GET')return;
 if(url.pathname.startsWith('/api/'))return;
 // فقط منابع هم‌مبدأ را از شبکه به گوگل نمی‌بریم (مثلاً تصاویر Openverse کش نمی‌شوند)
 if(url.origin!==self.location.origin)return;
 event.respondWith(caches.match(event.request).then(cached=>{
  if(cached)return cached;
  return fetch(event.request).then(response=>{
   if(response&&response.status===200&&response.type==='basic'){
    const copy=response.clone();
    caches.open(CACHE).then(cache=>cache.put(event.request,copy));
   }
   return response;
  }).catch(()=>{
   // فقط برای ناوبری به صفحهٔ اصلی برمی‌گردیم، نه برای تصویر یا اسکریپت
   if(event.request.mode==='navigate')return caches.match('/index.html');
   return Response.error();
  });
 }));
});
