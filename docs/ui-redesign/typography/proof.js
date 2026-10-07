'use strict';
// Diagnostic fixture page only: no product data, GPU, fetch or external requests.
(async()=>{
 await document.fonts.ready;
 const rangeWidth=el=>{const range=document.createRange();range.selectNodeContents(el);return range.getBoundingClientRect().width;};
 const probes=[...document.querySelectorAll('[data-expected]')].map((el,i)=>{
  const rendered=rangeWidth(el),expected=Number(el.dataset.expected),fallback=rangeWidth(document.getElementById(`fallback-${i}`));
  return {text:el.textContent,rendered_px:rendered,official_advance_px:expected,error_px:Math.abs(rendered-expected),system_fallback_px:fallback,distinguishes_system:Math.abs(rendered-fallback)>0.1,advance_match:Math.abs(rendered-expected)<0.12};
 });
 document.getElementById('font-evidence').textContent=JSON.stringify({
  fonts:[...document.fonts].map(f=>({family:f.family,weight:f.weight,status:f.status})),
  requests:performance.getEntriesByType('resource').filter(e=>e.name.endsWith('.woff2')).map(e=>({url:e.name,transfer_bytes:e.transferSize,decoded_bytes:e.decodedBodySize})),
  probes,all_advances_match:probes.every(p=>p.advance_match),
  limit:'IAB exposes no CDP / Rendered Fonts API. Glyph advances match decoded official font data; this is stronger than computed family alone, but not a native per-glyph font attribution.'
 },null,2);
})();
