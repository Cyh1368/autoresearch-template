import json,pathlib,subprocess,sys
p=pathlib.Path(__file__).resolve().parent; out=p/'output'; out.mkdir(exist_ok=True)
for i,x in enumerate((2,3)):
 r=subprocess.run([sys.executable,'-c',f'print({x}*{x})'],capture_output=True,text=True,check=True)
 (out/f'exp{i}.json').write_text(json.dumps({'measurement':int(r.stdout),'stdout':r.stdout}))
(out/'report.md').write_text('Baseline measurement 4; subsequent measurement 9; decision: retain change for demonstration.\n')
print('Smoke completed:',(out/'report.md'))
