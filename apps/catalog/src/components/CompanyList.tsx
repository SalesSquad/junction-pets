import type {Pet,RoleFilter} from '../types';
import {Icon} from './Icons';
const filters:Array<{id:RoleFilter;label:string}>= [{id:'all',label:'All'},{id:'challenge',label:'Challenge'},{id:'technology',label:'Technology'},{id:'more',label:'More'}];
export function CompanyList({all,filtered,query,onQuery,role,onRole,selected,onSelect}:{all:Pet[];filtered:Pet[];query:string;onQuery:(q:string)=>void;role:RoleFilter;onRole:(r:RoleFilter)=>void;selected:Pet|null;onSelect:(p:Pet)=>void}) {
 return <aside className="company-browser" aria-label="Choose a companion">
  <label className="search-field"><Icon name="search"/><span className="sr-only">Search companies</span><input type="search" placeholder="Search companies" value={query} onChange={e=>onQuery(e.target.value)} autoComplete="off"/></label>
  <div className="role-filters" aria-label="Filter by partner role">{filters.map(f=>{const count=all.filter(p=>f.id==='all'||(f.id==='more'?['main','collaborator'].includes(p.company.role):p.company.role===f.id)).length;return <button key={f.id} type="button" aria-pressed={role===f.id} onClick={()=>onRole(f.id)}>{f.label}<span>{count}</span></button>;})}</div>
  <p className="sr-only" role="status">{filtered.length} companions found</p>
  {filtered.length ? <><label className="mobile-company-select">Choose a company<select value={selected?.slug||''} onChange={e=>{const p=filtered.find(p=>p.slug===e.target.value);if(p)onSelect(p);}}>{!selected&&<option value="" disabled>Choose a company</option>}{filtered.map(p=><option value={p.slug} key={p.id}>{p.company.name}</option>)}</select></label><ul className="company-list">{filtered.map(p=><li key={p.id}><button type="button" aria-current={selected?.slug===p.slug?'true':undefined} onClick={()=>onSelect(p)}><span>{p.company.name}</span><Icon name="chevron"/></button></li>)}</ul></> : <div className="no-companies"><h2>No companies found</h2><p>Try another name or show all companions.</p><button type="button" className="text-button" onClick={()=>{onQuery('');onRole('all');}}>Clear filters</button></div>}
 </aside>;
}
