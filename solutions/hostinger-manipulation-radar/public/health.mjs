fetch('/api/status').then(r=>r.json()).then(s=>{
  for(const node of document.querySelectorAll('[data-service-status]'))node.textContent=s.hosting+' · AI Router '+s.aiRouter;
}).catch(()=>{for(const node of document.querySelectorAll('[data-service-status]'))node.textContent='Deployment status unavailable';});
