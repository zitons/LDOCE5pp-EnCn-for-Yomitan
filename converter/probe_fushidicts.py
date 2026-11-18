"""Import a real Yomitan package and query the unmodified fushidicts DLL.

The native database lives under --output; no installed app data is accessed.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path


class ImportResult(C.Structure):
    _fields_=[('success',C.c_int32),('title',C.c_void_p),('term_count',C.c_int32),
        ('meta_count',C.c_int32),('freq_count',C.c_int32),('pitch_count',C.c_int32),
        ('media_count',C.c_int32),('kanji_count',C.c_int32),('detected_type',C.c_void_p),('error',C.c_void_p)]


class Engine:
    def __init__(self,dll,package,output,transforms):
        self.dll=C.CDLL(str(Path(dll).resolve()))
        signatures={
            'fushidicts_create':([],C.c_void_p),
            'fushidicts_destroy':([C.c_void_p],None),
            'fushidicts_load_transforms':([C.c_void_p,C.c_char_p],None),
            'fushidicts_add_term_dict':([C.c_void_p,C.c_char_p],None),
            'fushidicts_import':([C.c_char_p,C.c_char_p,C.c_char_p],ImportResult),
            'fushidicts_free_import_result':([C.POINTER(ImportResult)],None),
            'fushidicts_lookup_popup_json':([C.c_void_p,C.c_char_p,C.c_int32,C.c_int32,C.c_int32],C.c_void_p),
            'fushidicts_free_string':([C.c_void_p],None)}
        for name,(args,result) in signatures.items():
            f=getattr(self.dll,name);f.argtypes=args;f.restype=result
        self.handle=self.dll.fushidicts_create()
        if not self.handle:raise RuntimeError('Native handle creation failed')
        out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
        stamp=out/'import.json';sha=hashlib.sha256(Path(package).read_bytes()).hexdigest()
        info=json.loads(stamp.read_text(encoding='utf8')) if stamp.exists() else {}
        if info.get('package_sha256')!=sha or not Path(info.get('directory','__missing__')).is_dir():
            result=self.dll.fushidicts_import(str(Path(package).resolve()).encode(),str(out).encode(),None)
            try:
                if not result.success:raise RuntimeError(C.string_at(result.error).decode() if result.error else 'Native import failed')
                title=C.string_at(result.title).decode()
                info={'package_sha256':sha,'title':title,'term_count':result.term_count,'directory':str(out/title)}
                stamp.write_text(json.dumps(info,indent=2),encoding='utf8')
            finally:self.dll.fushidicts_free_import_result(C.byref(result))
        self.info=info
        for path in transforms:self.dll.fushidicts_load_transforms(self.handle,Path(path).read_bytes())
        self.dll.fushidicts_add_term_dict(self.handle,info['directory'].encode())

    def lookup(self,text,scan=64):
        ptr=self.dll.fushidicts_lookup_popup_json(self.handle,text.encode(),32,scan,32)
        if not ptr:raise RuntimeError('Native lookup returned null')
        try:
            rows=json.loads(C.string_at(ptr).decode())
            return [{'expression':r['expression'],'matched':r['matched'],'trace':r['deinflectionTrace']} for r in rows]
        finally:self.dll.fushidicts_free_string(ptr)

    def close(self):
        if self.handle:self.dll.fushidicts_destroy(self.handle);self.handle=None


PROBES=['pick up','picked it up','picked John up','took it all out','look the word up',
    'give Mary a hand','gave him a hand','give a hand','hang by a thread','hanging by a thread',
    'fire engines','half truth','self explanatory','pen up','penned him in','brick in','bricked it in',
    'hang up your football boots','work up a thirst']


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dll',required=True);ap.add_argument('--package',required=True)
    ap.add_argument('--output',required=True);ap.add_argument('--transforms',required=True)
    args=ap.parse_args();tf=Path(args.transforms)
    engine=Engine(args.dll,args.package,args.output,[tf/'en.json',tf/'en_irregular.json'])
    try:
        probes={q:{str(scan):engine.lookup(q,scan) for scan in (16,64)} for q in PROBES}
        report={'engine':'Unmodified fushidicts source compiled locally; real native importer and Lookup::lookup',
            'dll_sha256':hashlib.sha256(Path(args.dll).read_bytes()).hexdigest(),
            'import':engine.info,'probes':probes}
        (Path(args.output)/'probe_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    finally:engine.close()


if __name__=='__main__':main()
