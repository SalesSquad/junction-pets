export const PRODUCT = Object.freeze({name:'Logitech MX Master 3S Bluetooth Edition',mpn:'910-007501',gtin:'5099206129382',quantity:1});
export const TTL_MS = 5 * 60_000;
export const SOURCES = Object.freeze([
  Object.freeze({id:'gigantti',name:'Gigantti',url:'https://www.gigantti.fi/product/tietokoneet-ja-toimistotarvikkeet/tietokonetarvikkeet/hiiret-ja-nappaimistot/tietokoneen-hiiret/logitech-mx-master-3s-langaton-hiiri-grafiitti/976944'}),
  Object.freeze({id:'proshop',name:'Proshop',url:'https://www.proshop.fi/Hiiret/Logitech-MX-Master-3S-Bluetooth-Edition-Ergonominen-hiiri-Optinen-7-painiketta-Harmaa/3400336'})
]);
export function sourceById(id) { const source=SOURCES.find(s=>s.id===id); if(!source) throw Error('SOURCE_NOT_ALLOWED'); return source; }
