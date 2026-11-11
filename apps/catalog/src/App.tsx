import {useEffect,useMemo,useState} from 'react';
import {matches,parseCatalogue,parseHost} from './catalog';
import {publicAsset} from './paths';
import type {Catalogue,HostConfig,Pet,RoleFilter} from './types';
import {CompanyList} from './components/CompanyList';
import {PetDetail} from './components/PetDetail';
import {QrDialog} from './components/QrDialog';

type State={catalogue:Catalogue;config:HostConfig}|null;
export default function App(){
 const [data,setData]=useState<State>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 const [query,setQuery]=useState(''),[role,setRole]=useState<RoleFilter>('all'),[selectedSlug,setSelectedSlug]=useState(()=>new URLSearchParams(window.location.search).get('pet')||'junction-mariadb'),[qrPet,setQrPet]=useState<Pet|null>(null);
 useEffect(()=>{const controller=new AbortController();setError('');const read=async(path:string)=>{const response=await fetch(publicAsset(path),{signal:controller.signal});if(!response.ok)throw new Error('The companion collection could not be loaded. Please try again.');return response.json();};void Promise.all([read('catalog.json'),read('host-config.json')]).then(([catalogue,host])=>setData({catalogue:parseCatalogue(catalogue),config:parseHost(host)})).catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:'The collection could not be loaded.');});return ()=>controller.abort();},[retry]);
 const filtered=useMemo(()=>data?.catalogue.pets.filter(p=>matches(p,query,role))||[],[data,query,role]);
 const selected=filtered.find(p=>p.slug===selectedSlug)||filtered[0]||null;
 function select(pet:Pet){setSelectedSlug(pet.slug);const url=new URL(window.location.href);url.searchParams.set('pet',pet.slug);window.history.replaceState(null,'',url);}
 useEffect(()=>{const onHistory=()=>setSelectedSlug(new URLSearchParams(window.location.search).get('pet')||'junction-mariadb');window.addEventListener('popstate',onHistory);return ()=>window.removeEventListener('popstate',onHistory);},[]);
 return <><a className="skip-link" href="#collection-main">Skip to companions</a><div className="page-shell"><header className="site-header"><a className="wordmark" href={data?`${data.config.canonicalOrigin}/studio`:'#collection-main'} aria-label="Chibi home">chibi.pet</a><nav aria-label="Main navigation"><a href="#collection-main" aria-current="page">Junction</a>{data&&<a href={`${data.config.canonicalOrigin}/${data.config.locale}/den`}>My Chibi</a>}</nav></header><main id="collection-main"><div className="collection-heading"><h1>Junction companions</h1><p>Meet the companies. Find your companion.</p></div>{error?<section className="load-state" role="alert"><h2>Let's try that again</h2><p>{error}</p><button type="button" className="button button-primary" onClick={()=>setRetry(v=>v+1)}>Retry</button></section>:!data?<div className="load-state" role="status">Opening the companion collection…</div>:<div className="catalogue-layout"><CompanyList all={data.catalogue.pets} filtered={filtered} query={query} onQuery={setQuery} role={role} onRole={setRole} selected={selected} onSelect={select}/>{selected?<PetDetail key={selected.id} pet={selected} config={data.config} onQr={()=>setQrPet(selected)}/>:<section className="detail-empty"><h2>A companion for your next idea.</h2><p>Clear the search to explore the company collection.</p></section>}</div>}</main><footer className="site-footer"><span>Built by Chibi for conversations that go somewhere.</span><span>Independent company companions</span></footer></div>{qrPet&&data&&<QrDialog pet={qrPet} config={data.config} onClose={()=>setQrPet(null)}/>}</>;
}
