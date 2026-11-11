import type {SVGProps} from 'react';
type IconName='arrow'|'chevron'|'search'|'qr'|'copy'|'external'|'download'|'close'|'check';
const paths:Record<IconName,string>= {
  arrow:'M4 12h15M13 5l7 7-7 7', chevron:'m9 5 7 7-7 7', search:'m16 16 5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  qr:'M3 3h6v6H3zM15 3h6v6h-6zM3 15h6v6H3zM15 15h2v2h-2zM19 19h2v2h-2zM19 13h2v4M13 19v2h4',
  copy:'M8 8h12v13H8zM4 16H3V3h12v1',external:'M13 3h8v8M21 3 11 13M9 3H3v18h18v-6',
  download:'M12 3v12M6 10l6 6 6-6M3 17v4h18v-4',close:'m5 5 14 14M5 19 19 5',check:'m4 12 5 5L20 6'
};
export function Icon({name,...props}:SVGProps<SVGSVGElement>&{name:IconName}) {
 return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name]}/></svg>;
}
