import json,os,shutil,numpy as np
fmt=lambda v,d=0: f'{v:.{d}f}'.replace('.',',')
S={}
txt={
 'grip':dict(name='Voimapuristus',kicker='Dynamometritesti',what='Simuloitu hanska antaa kolme puristusporrasta. Robottikäden sormenpäät seuraavat ihmisen sormenpäitä, ja kiinteä tanko toimii puristusvoimamittarina. Sormet värjäytyvät sitä kuumemmiksi, mitä kovempaa ne painavat.'),
 'pinch':dict(name='Nipistysote',kicker='Peukalo ja etusormi',what='Hanskan peukalon ja etusormen sulkeutuminen ohjaa robotin nipistysotetta. Kun sormet jo koskevat mittapalaa, lisäsulkeutuminen muutetaan puristuskäskyksi, koska ihmisen sormet eivät voi mennä esineen läpi.'),
 'fragile':dict(name='Hauras esine',kicker='Kolme tapaa pitää kiinni',what='Sama esine kolmesti. Ensin operaattori sulkee käden silmämääräisesti ilman tuntoa ja esine rikkoutuu. Sitten operaattori näkee ja kuulee robotin tunteman voiman ja pysähtyy viiteen newtoniin. Lopuksi operaattori puristaa täysillä, mutta käsi rajoittaa voiman itse kolmeen newtoniin.'),
 'slip':dict(name='Luistorefleksi',kicker='Ote kiristyy kuorman mukaan',what='Tankoa vedetään kasvavalla voimalla, ja operaattori pitää kätensä paikallaan. Ensin käsi pitää vakio-otteen ja tanko luistaa. Toisella kerralla käsi tuntee leikkausvoiman kohinaisista tuntoantureistaan ja kiristää otetta itse.'),
 'cup':dict(name='Nosto ja kaato',kicker='Käsi liikkuu kuusiakselisella kannattimella',what='Käsi lähestyy pulloa sivulta, tarttuu, nostaa, siirtää, kallistaa kuin kaataisi ja laskee pullon takaisin pystyyn. Pullo on vapaa 300 gramman kappale, joka pysyy kädessä vain kitkan varassa.'),
}
for n in ['grip','pinch','fragile','slip','cup']:
    j=json.load(open(f'out/{n}.json')); d=j['data']; m=j['meta']
    s=dict(id=n,**txt[n],metric='Voima',t=[r['t'] for r in d],total=[r['total'] for r in d],fingers=[r['fingers'] for r in d],human=[r['human'] for r in d],sk=[r['sk'] for r in d],chips=[],lines=[],series2=None,flags=[r.get('flag') for r in d] if 'flag' in d[0] else None,ev=[])
    tot=np.array(s['total'])
    if n=='grip':
        st=float(np.mean([r['total'] for r in d if 6.0<r['t']<6.7])); s['metric']='Puristusvoima (4 sormea, netto)'
        s['chips']=[['Täysi puristus, vakaa',fmt(st)+' N'],['Hetkellinen huippu',fmt(tot.max())+' N'],['Ihmisen keskiarvo','538 N'],['Osuus ihmisestä',fmt(st/538*100)+' %']]
    if n=='pinch':
        s['metric']='Nipistysvoima (heikompi sormi)'; s['chips']=[['Suurin nipistys',fmt(tot.max())+' N'],['Ihmisen keskiarvo','n. 80 N'],['Osuus ihmisestä',fmt(tot.max()/80*100)+' %']]
    if n=='fragile':
        s['metric']='Puristusvoima'; s['chips']=[['Ilman palautetta, huippu',fmt(m['blind']['peak'],1)+' N'],['Voimapalautteella',fmt(m['feedback']['steady'],1)+' N'],['Käden voimarajalla',fmt(m['limiter']['steady'],1)+' N']]
        s['lines']=[[15,'rikkoutuu 15 N','crit'],[5,'operaattorin tavoite 5 N','ok']]
    if n=='slip':
        s['metric']='Otevoima'; s['series2']=dict(name='vetokuorma',v=[r['load'] for r in d])
        s['chips']=[['Luistaa vakio-otteella',fmt(m['slip_at'])+' N'],['Luistaa refleksin kanssa',fmt(m['slip_at_reflex'])+' N'],['Parannus',fmt(m['slip_at_reflex']/m['slip_at'],1)+'×']]
    if n=='cup':
        s['metric']='Otevoima (N)'; s['series2']=dict(name='pullon korkeus (mm)',v=[max(0,r['height']) for r in d])
        s['chips']=[['Nostokorkeus',fmt(max(r['height'] for r in d))+' mm'],['Siirto sivulle',fmt(m['moved_x_mm'])+' mm'],['Suurin kallistus',fmt(max(r['tilt'] for r in d))+'°'],['Lopuksi pystyssä','kyllä' if m['final_tilt']<3 else 'ei']]
    if s['flags']:
        prev=False
        for i,f in enumerate(s['flags']):
            hit=('RIKKI' in f) or ('LUISTI' in f)
            if hit and not prev: s['ev'].append(i)
            prev=hit
    s['fmax']=float(max(max(f) for f in s['fingers'])) or 1
    s['ymax']=float(max(tot.max(),max(s['series2']['v']) if s['series2'] else 0,max([l[0] for l in s['lines']],default=0))*1.12)
    S[n]=s; os.path.exists(f'out/{n}.mp4') and shutil.copy(f'out/{n}.mp4',f'site/{n}.mp4'); print(n,s['chips'],s['ev'])
# evidence
E={}
import glove
for k in ['power']:
    e=np.array(json.load(open(f'lut_{k}.json'))['err'])*1000; E['ret_mean']=fmt(e.mean(),2); E['ret_max']=fmt(e.max(),1)
fb=json.load(open('results/exp_feedback.json')); E['fb']=[[k,v['broken'],v['n'],fmt(np.mean(v['steady']),1),fmt(max(v['peak']),1)] for k,v in fb.items()]
fr=json.load(open('results/exp_friction.json')); E['fr']=[[fmt(r['mu'],1),fmt(r['no_reflex']),fmt(r['reflex']),fmt(r['reflex_ideal'])] for r in fr]
ln=json.load(open('results/exp_learn.json')); E['bc']=dict(ok=ln['success'],n=ln['n'],samples=ln['samples'],demos=ln['demos'],err=fmt(np.mean([abs(t['final']-t['target'])/t['target']*100 for t in ln['tests']]),1))
html=open('template.html').read().replace('/*DATA*/',json.dumps(S,ensure_ascii=False,separators=(',',':'))).replace('/*EV*/',json.dumps(E,ensure_ascii=False))
open('site/index.html','w').write(html); print(len(html)//1024,'KB',E)
