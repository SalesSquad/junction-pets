import type {CSSProperties} from 'react';
import type {Pet} from '../types';
import {publicAsset} from '../paths';
export function PetArt({pet,small=false}:{pet:Pet;small?:boolean}) {
 const col=pet.artIndex%6,row=Math.floor(pet.artIndex/6);
 return <div className={`pet-art${small?' pet-art--small':''}`} role="img" aria-label={`Original ${pet.company.name} companion illustration`} style={{backgroundImage:`url('${publicAsset('assets/company-mascots.png')}')`,backgroundPosition:`${col*20}% ${row*20}%`} as CSSProperties}/>;
}
