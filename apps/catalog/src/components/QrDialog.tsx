import {useEffect,useRef,useState} from 'react';
import QRCode from 'qrcode';
import type {Pet,HostConfig} from '../types';
import {copyText,petAvailable,petUrl} from '../catalog';
import {PetArt} from './PetArt';
import {Icon} from './Icons';
export function QrDialog({pet,config,onClose}:{pet:Pet;config:HostConfig;onClose:()=>void}) {
 const ref=useRef<HTMLDialogElement>(null),[qr,setQr]=useState(''),[error,setError]=useState(''),[copied,setCopied]=useState(false),[copyNotice,setCopyNotice]=useState('');
 const url=petUrl(config,pet),available=petAvailable(config,pet);
 useEffect(()=>{const dialog=ref.current;dialog?.showModal();return ()=>dialog?.close();},[]);
 useEffect(()=>{let current=true;void QRCode.toDataURL(url,{width:720,margin:4,errorCorrectionLevel:'M',color:{dark:'#171c1c',light:'#ffffff'}}).then(data=>{if(current)setQr(data);}).catch(()=>{if(current)setError('The QR code could not be generated. The link is available below.');});return ()=>{current=false;};},[url]);
 async function copyLink(){const success=await copyText(url);setCopied(success);setCopyNotice(success?'Link copied.':'Copy is unavailable in this browser. Select the link above to copy it.');}
 function close(){ref.current?.close();onClose();}
 return <dialog ref={ref} className="qr-dialog" aria-labelledby="qr-title" aria-describedby="qr-description" onCancel={e=>{e.preventDefault();close();}}><button type="button" className="close-button" aria-label="Close QR code" onClick={close}><Icon name="close"/></button><PetArt pet={pet} small/><h2 id="qr-title">{pet.displayName}</h2><p id="qr-description">{available?'Scan to meet your pet. Sign in to Chibi and review its profile before adopting.':'Preview only. Recipient adoption is not open yet. This code points to the future Chibi product page.'}</p>{qr?<img className="qr-image" src={qr} width="240" height="240" alt={`QR code for ${pet.displayName} on Chibi`}/>:<p role="status">{error||'Preparing QR code…'}</p>}<label className="share-link">Pet page<input type="url" value={url} readOnly onFocus={e=>e.target.select()}/></label><div className="qr-actions"><button type="button" className="button button-secondary" onClick={()=>void copyLink()}><Icon name={copied?'check':'copy'}/>{copied?'Copied':'Copy link'}</button>{qr&&<a className="button button-primary" href={qr} download={`${pet.slug}-qr.png`}><Icon name="download"/>Download QR</a>}</div><p role="status" className="qr-copy-notice">{copyNotice}</p><p className="qr-footnote">This public link contains no login token and gives no account access.</p></dialog>;
}
