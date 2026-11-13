import test from 'node:test';
import assert from 'node:assert/strict';
import {planResponsiveMedia} from '../pets/cloudinary/responsive-media.mjs';

const fixture = () => ({
  asset: {id:'fictional-mascot', width:1280, height:960, visibility:'public', decorative:false, alt:'An invented blue mascot', metadata:{credit:'Fictional studio'}},
  variants: [{width:640, format:'webp', quality:80}, {width:320, format:'avif', quality:65}],
});
const plan = input => planResponsiveMedia(JSON.stringify(input));

test('plans exact responsive dimensions without provider effects', () => {
  const input=fixture(), before=structuredClone(input), result=plan(input);
  assert.deepEqual(input,before);
  assert.equal(result.status,'planned');
  assert.equal(result.assetId,'fictional-mascot');
  assert.deepEqual(result.variants,[
    {width:320,height:240,format:'avif',quality:65,fit:'contain'},
    {width:640,height:480,format:'webp',quality:80,fit:'contain'},
  ]);
  assert.deepEqual(result.publicMetadata,{alt:'An invented blue mascot',credit:'Fictional studio'});
  for(const name of ['transformationExecuted','deliveryVerified','pixelsInspected','rightsVerified']) assert.equal(result[name],false);
  assert.equal('url' in result,false);
});

test('same requested set has stable order and exact supported boundaries', () => {
  const a=fixture(), b=fixture(); b.variants.reverse();
  assert.deepEqual(plan(a),plan(b));
  a.asset.width=1920; a.asset.height=1080;
  a.variants=[{width:1920,format:'jpeg',quality:100},{width:160,format:'avif',quality:1}];
  assert.deepEqual(plan(a).variants.map(v=>[v.width,v.height]),[[160,90],[1920,1080]]);
});

test('rejects unsupported width, unsafe dimensions and guessed numeric units', () => {
  for(const width of [0,161,4096,320.5,'320',null]) {
    const x=fixture(); x.variants[0].width=width; assert.throws(()=>plan(x),TypeError);
  }
  for(const width of [0,-1,16385,Number.MAX_SAFE_INTEGER,'1280']) {
    const x=fixture(); x.asset.width=width; assert.throws(()=>plan(x),TypeError);
  }
});

test('rejects unsupported formats, fractional quality and quality outside bounds', () => {
  for(const format of ['gif','png','auto','WEBP',null]) {
    const x=fixture(); x.variants[0].format=format; assert.throws(()=>plan(x),TypeError);
  }
  for(const quality of [0,101,0.5,'80',null]) {
    const x=fixture(); x.variants[0].quality=quality; assert.throws(()=>plan(x),TypeError);
  }
});

test('rejects upscaling and unbounded output height rather than quietly clamping', () => {
  const x=fixture(); x.asset.width=319;
  assert.throws(()=>plan(x),/upscale/);
  x.asset.width=640; x.asset.height=16384;
  assert.throws(()=>plan(x),/height/);
});

test('rejects duplicate width-format pairs, empty and oversized variant lists', () => {
  const x=fixture(); x.variants.push({...x.variants[0],quality:20});
  assert.throws(()=>plan(x),/duplicate/);
  x.variants=[]; assert.throws(()=>plan(x),TypeError);
  x.variants=Array.from({length:19},()=>fixture().variants[0]); assert.throws(()=>plan(x),TypeError);
});

test('denies private or unknown visibility and rejects metadata passthrough', () => {
  for(const visibility of ['private','authenticated','unknown',null]) {
    const x=fixture(); x.asset.visibility=visibility; assert.throws(()=>plan(x),TypeError);
  }
  for(const field of ['gps','email','signedUrl','exif','__proto__']) {
    const x=fixture(); Object.defineProperty(x.asset.metadata,field,{value:'fictional-sensitive',enumerable:true});
    assert.throws(()=>plan(x),/unknown field/);
  }
});

test('requires useful supplied alt for meaningful images and empty alt for decorative ones', () => {
  const x=fixture(); x.asset.alt='   '; assert.throws(()=>plan(x),TypeError);
  x.asset.decorative=true; x.asset.alt=''; assert.equal(plan(x).publicMetadata.alt,'');
  x.asset.alt='not empty'; assert.throws(()=>plan(x),TypeError);
  x.asset.decorative='true'; assert.throws(()=>plan(x),TypeError);
});

test('rejects malformed, oversized, executable or unknown schema input', () => {
  for(const value of [fixture(),null,42,'{','null','[]',' '.repeat(16385)]) assert.throws(()=>planResponsiveMedia(value),TypeError);
  for(const pick of [x=>x,x=>x.asset,x=>x.variants[0]]) {
    const x=fixture(); pick(x).deliveryVerified=true; assert.throws(()=>plan(x),/unknown field/);
  }
  const x=fixture(); delete x.asset.metadata; assert.throws(()=>plan(x),/missing field/);
  x.asset.metadata={credit:'line\nbreak'}; assert.throws(()=>plan(x),TypeError);
});

test('does not accept external asset identifiers or silently certify supplied rights', () => {
  for(const id of ['https://private.invalid/asset?token=fictional','../photo','',null]) {
    const x=fixture(); x.asset.id=id; assert.throws(()=>plan(x),TypeError);
  }
  const x=fixture(); x.asset.metadata={credit:'Supplied claim; not verified'};
  assert.equal(plan(x).rightsVerified,false);
  x.asset.metadata.rightsVerified=true; assert.throws(()=>plan(x),TypeError);
});
