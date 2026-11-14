#!/usr/bin/env python3
"""Bounded read-only HTTP ZIP range access for an immutable public benchmark.

No full 2.35GB archive download, no extraction, no images written to disk.
CRC checks per member; HF original archive hash is asserted from source header,
NOT independently hashed over the complete remote file.
"""
from __future__ import annotations
import dataclasses
import re
import struct
import urllib.request
import zlib

EOCD=struct.Struct("<4s4H2IH")
CD=struct.Struct("<4s6H3I5H2I")
LH=struct.Struct("<4s5H3I2H")
RANGE=re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
MAX_TOTAL=3_000_000_000
MAX_CD=18_000_000


@dataclasses.dataclass(frozen=True)
class Member:
    name: str
    comp: int
    uncomp: int
    crc32: int
    method: int
    offset: int
    flags: int


class ZipHTTP:
    def __init__(self, url: str, expected_sha: str, expected_size: int):
        self.url=url
        self.size=expected_size
        if not re.fullmatch(r"[a-f0-9]{64}",expected_sha) or not 1024<self.size<MAX_TOTAL:
            raise ValueError("Unpinned remote source or archive size")
        # HEAD through HuggingFace portal proves origin pointer, never signed
        # provider attestation or verification of bytes not transferred.
        req=urllib.request.Request(url,method="HEAD")
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, message, headers, redirect_url):
                return None
        try:
            with urllib.request.build_opener(NoRedirect).open(req,timeout=20) as r:
                headers=r.headers
        except urllib.error.HTTPError as e:
            if e.code != 302:
                raise
            headers=e.headers
        found=headers.get("x-linked-etag", "").strip('"')
        actual=int(headers.get("x-linked-size","0"))
        if found!=expected_sha or actual!=expected_size:
            raise RuntimeError(f"HF archive pointer mismatch: size {actual}, digest matches {found==expected_sha}")
        # Reuse public CDN redirect for many bounded requests; refresh
        # through the official origin only if the presigned URL expires.
        self.download_url=headers.get("Location",self.url)
        tail=self.get(max(0,self.size-130000),self.size)
        marker=tail.rfind(b"PK\x05\x06")
        if marker<0:raise RuntimeError("End-of-central-directory not found")
        _,disk,cd_disk,on_disk,entries,cd_size,cd_offset,comment=EOCD.unpack_from(tail,marker)
        if disk or cd_disk or on_disk!=entries or entries==0 or entries>=65000 or not 0<cd_size<MAX_CD or cd_offset+cd_size>self.size:
            raise RuntimeError("Unsafe central directory offsets")
        data=self.get(cd_offset,cd_offset+cd_size)
        self.members={}
        pos=0
        for i in range(entries):
            if data[pos:pos+4]!=b"PK\x01\x02":
                raise RuntimeError("Incorrect central directory entry")
            t=CD.unpack_from(data,pos)
            _,made,need,flags,method,_,_,crc,csize,usize,nlen,elen,clen,diskstart,_,_,offset=t
            raw=data[pos+CD.size:pos+CD.size+nlen]
            name=raw.decode("utf8" if flags & 0x800 else "cp437")
            if diskstart:
                raise RuntimeError("Multi-disk archive rejected")
            if (csize==0xFFFFFFFF or usize==0xFFFFFFFF or offset==0xFFFFFFFF):
                # ZIP64 extra order: uncompressed size, compressed size,
                # local-header offset, disk-start; fields only when sentinel.
                extra=data[pos+CD.size+nlen:pos+CD.size+nlen+elen]
                extra_pos=0
                found=False
                while extra_pos+4<=len(extra):
                    tag,length=struct.unpack_from("<HH",extra,extra_pos)
                    payload=extra[extra_pos+4:extra_pos+4+length]
                    if tag==1:
                        cursor=0
                        if usize==0xFFFFFFFF:
                            usize=struct.unpack_from("<Q",payload,cursor)[0];cursor+=8
                        if csize==0xFFFFFFFF:
                            csize=struct.unpack_from("<Q",payload,cursor)[0];cursor+=8
                        if offset==0xFFFFFFFF:
                            offset=struct.unpack_from("<Q",payload,cursor)[0];cursor+=8
                        found=True
                        break
                    extra_pos+=4+length
                if not found or csize>=MAX_TOTAL or usize>=MAX_TOTAL:
                    raise RuntimeError("Unsupported ZIP64 member")
            if (not name or name.startswith("/") or "\\" in name
                or ".." in name.split("/") or name in self.members or
                not 0<=offset<self.size or method not in (0,8)):
                raise RuntimeError("Unsafe remote ZIP member")
            self.members[name]=Member(name,csize,usize,crc,method,offset,flags)
            pos+=CD.size+nlen+elen+clen
        if pos!=len(data):
            raise RuntimeError("Central directory trailing garbage")

    def get(self,start:int,end:int)->bytes:
        if not 0<=start<end<=self.size or end-start>MAX_CD:
            raise RuntimeError("Unsafe remote ZIP byte range")
        for url in (self.download_url,self.url):
            req=urllib.request.Request(url,headers={"Range":f"bytes={start}-{end-1}"})
            try:
                with urllib.request.urlopen(req,timeout=45) as r:
                    header=r.headers.get("Content-Range","")
                    match=RANGE.match(header)
                    if r.status!=206 or not match or (int(match[1]),int(match[2])+1,int(match[3]))!=(start,end,self.size):
                        raise RuntimeError(f"Unexpected HTTP range response {r.status}, {header}")
                    block=r.read(end-start+1)
                if len(block)!=end-start:
                    raise RuntimeError("Truncated remote archive response")
                return block
            except urllib.error.HTTPError as exc:
                if exc.code not in (403,404,429) or url==self.url:
                    raise
                # Expired ephemeral public CDN URL: retry only once via
                # official HF origin, not by broadening credentials/access.
                continue
        raise RuntimeError("No official range route available")

    def read(self,name:str,max_size:int=10_000_000)->bytes:
        m=self.members[name]
        if m.uncomp>max_size or m.comp>max_size:
            raise RuntimeError("Member exceeds research budget")
        h=self.get(m.offset,m.offset+LH.size)
        t=LH.unpack(h)
        if t[0]!=b"PK\x03\x04" or t[3]!=m.method:
            raise RuntimeError("ZIP local header inconsistent")
        filename_len,extra_len=t[-2:]
        start=m.offset+LH.size+filename_len+extra_len
        data=self.get(start,start+m.comp)
        decoded=zlib.decompress(data,-zlib.MAX_WBITS) if m.method==8 else data
        if len(decoded)!=m.uncomp or zlib.crc32(decoded)&0xffffffff !=m.crc32:
            raise RuntimeError("Member CRC or original length mismatch")
        return decoded
