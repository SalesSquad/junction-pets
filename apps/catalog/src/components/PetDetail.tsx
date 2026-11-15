import {useState} from 'react';
import type {HostConfig,Pet} from '../types';
import {copyText,petAvailable,petUrl,safeHttps} from '../catalog';
import {Icon} from './Icons';
import {PetArt} from './PetArt';
import {publicAsset} from '../paths';
export function PetDetail({pet,config,onQr}:{pet:Pet;config:HostConfig;onQr:()=>void}) {
 const [copied,setCopied]=useState<number|null>(null),[notice,setNotice]=useState('');
 const available=petAvailable(config,pet);
 const packageBase=publicAsset(`packages/${encodeURIComponent(pet.company.slug)}`);
 async function copyPrompt(prompt:string,index:number){const ok=await copyText(prompt);setCopied(ok?index:null);setNotice(ok?'Question copied.':'Select the question text to copy it on this browser.');}
 return <article className="pet-detail" aria-labelledby="pet-title">
  <section className="pet-hero"><PetArt pet={pet}/><div className="pet-intro"><p className="pet-name">{pet.displayName}</p><h2 id="pet-title" tabIndex={-1}>{pet.tagline}</h2><p className="intro-copy">{pet.introduction}</p><div className="primary-actions">{available?<a className="button button-primary" href={petUrl(config,pet)}>Meet your pet<Icon name="arrow"/></a>:<button type="button" className="button button-primary" disabled aria-describedby="pet-availability">Meet your pet<Icon name="arrow"/></button>}<button type="button" className="button button-secondary" onClick={onQr}><Icon name="qr"/>{available?'Show QR code':'Preview QR code'}</button></div><p className="availability-copy" id="pet-availability">{available?'Continue in Chibi to sign in, review the pet and make it yours.':'Adoption and conversation are being prepared. Explore the profile and instructions now.'}</p></div></section>
  <section className="detail-section"><h3>What we can work on</h3><dl className="capabilities">{pet.capabilities.map(c=><div key={c.id}><dt>{c.title}{c.requiresConnection&&<span className="connection-note">Connection needed</span>}</dt><dd>{c.description}</dd></div>)}</dl></section>
  {!!pet.specialCapabilities?.length&&<section className="detail-section"><h3>Special capabilities</h3><dl className="capabilities special-capabilities">{pet.specialCapabilities.map(c=><div key={c.id}><dt>{c.title}<span className="connection-note">{c.status==='offline-demo'?'Offline demo in source':c.status==='needs-host-connection'?'Needs a host connection':'Source only'}</span></dt><dd>{c.description}</dd></div>)}</dl></section>}
  <section className="detail-section questions"><h3>Start with a question</h3><ul>{pet.starterPrompts.map((p,i)=><li key={p}><p>{p}</p><button type="button" aria-label={`Copy question ${i+1}`} onClick={()=>void copyPrompt(p,i)}><Icon name={copied===i?'check':'copy'}/><span>{copied===i?'Copied':'Copy'}</span></button></li>)}</ul><p className="sr-only" role="status">{notice}</p></section>
  <section className="detail-section source-section"><div><h3>Official sources</h3><ul className="source-links">{pet.sources.map(s=>safeHttps(s.url)?<li key={s.id}><a href={safeHttps(s.url)!} target="_blank" rel="noopener noreferrer"><Icon name="external"/>{s.title}</a></li>:null)}</ul></div><p className="independence-note">An independent companion, created by Chibi. Company endorsement is not implied. Connections are enabled separately in Chibi.</p></section>
  <section className="package-downloads" aria-label="Take the companion profile with you"><p>Take a closer look</p><a href={`${packageBase}/profile.json`} download><Icon name="download"/>Profile</a><a href={`${packageBase}/AGENTS.md`} download><Icon name="download"/>Agent instructions</a><a href={`${packageBase}/STORY.md`} download><Icon name="download"/>Companion story</a></section>
  {pet.sourceEvidence.notes && <details className="source-note"><summary>About this profile</summary><p>{pet.sourceEvidence.notes}</p></details>}
 </article>;
}
