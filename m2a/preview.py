import json
from .export import PARENTS


def write_preview(path, joints, fps, metadata, parents=None, label="SMPL-X skeleton", hint=None):
    import math
    step=max(1,math.ceil(len(joints)/600))
    joints=joints[::step]
    fps=fps/step
    payload = json.dumps(dict(source_step=step,joints=joints.round(5).tolist(),parents=PARENTS if parents is None else parents,fps=fps,source_start=metadata['start_frame']),separators=(',',':'))
    html = '''<!doctype html><html lang="ja"><meta charset="utf-8"><title>Movie2Anim · Standalone preview</title>
<style>body{margin:0;background:#101622;color:#e5edf8;font:15px system-ui}header{padding:18px 26px;border-bottom:1px solid #344058}h1{font-size:22px;margin:0 0 6px}p{margin:0;color:#9caec7}canvas{display:block;width:100vw;height:72vh;touch-action:none}footer{padding:15px 26px}button{padding:9px 20px;background:#4778ef;border:0;color:white;border-radius:6px;cursor:pointer}input{width:65%;vertical-align:middle}#frame{margin-left:20px}.hint{font-size:13px;margin-top:14px}</style>
<header><h1>Movie2Anim / Standalone</h1><p>SMPL-X skeleton · Y-up · drag to orbit / wheel to zoom</p></header>
<canvas id="c"></canvas><footer><button id="play">Play</button> <input id="seek" type="range" min="0" step="1" value="0"><span id="frame"></span><p class="hint">Research prototype: static person ROI. Foot-lock optimizer and Manny retargeting are not applied.</p></footer>
<script>const data=PAYLOAD;const c=document.getElementById('c'),ctx=c.getContext('2d'),seek=document.getElementById('seek');seek.max=data.joints.length-1;
let yaw=.35,pitch=.13,zoom=1,playing=false,start=0,drag=null;const xs=data.joints.flat().map(p=>p[0]),zs=data.joints.flat().map(p=>p[2]);const cx=(xs.reduce((a,b)=>Math.min(a,b),Infinity)+xs.reduce((a,b)=>Math.max(a,b),-Infinity))/2,cz=(zs.reduce((a,b)=>Math.min(a,b),Infinity)+zs.reduce((a,b)=>Math.max(a,b),-Infinity))/2;
function resize(){c.width=c.clientWidth*devicePixelRatio;c.height=c.clientHeight*devicePixelRatio;}addEventListener('resize',resize);resize();
function project(p){let x=p[0]-cx,y=p[1]-.9,z=p[2]-cz;let a=x*Math.cos(yaw)-z*Math.sin(yaw),b=x*Math.sin(yaw)+z*Math.cos(yaw);let yy=y*Math.cos(pitch)-b*Math.sin(pitch),zz=y*Math.sin(pitch)+b*Math.cos(pitch);let s=c.height*.34*zoom/(1+zz*.08);return [c.width/2+a*s,c.height*.53-yy*s];}
function line(a,b,color,width=1){a=project(a);b=project(b);ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.strokeStyle=color;ctx.lineWidth=width*devicePixelRatio;ctx.stroke();}
function draw(t){if(playing)seek.value=Math.floor((t-start)/1000*data.fps)%data.joints.length;let i=Number(seek.value);ctx.clearRect(0,0,c.width,c.height);for(let k=-5;k<=5;k++){line([cx+k*.5,0,cz-2.5],[cx+k*.5,0,cz+2.5],'#273448');line([cx-2.5,0,cz+k*.5],[cx+2.5,0,cz+k*.5],'#273448');}const j=data.joints[i];for(let b=1;b<j.length;b++)line(j[b],j[data.parents[b]],b<25?'#69befa':'#5c7ea6',b<25?3:1);for(let b=0;b<22;b++){let p=project(j[b]);ctx.beginPath();ctx.arc(...p,3*devicePixelRatio,0,Math.PI*2);ctx.fillStyle='#eaf6ff';ctx.fill();}document.getElementById('frame').textContent=`${i+1} / ${jointsCount()} · source ${data.source_start+i*(data.source_step||1)}F`;requestAnimationFrame(draw);}
function jointsCount(){return data.joints.length}document.getElementById('play').onclick=()=>{playing=!playing;start=performance.now()-Number(seek.value)/data.fps*1000;document.getElementById('play').textContent=playing?'Pause':'Play';};seek.oninput=()=>{playing=false;document.getElementById('play').textContent='Play';};c.onpointerdown=e=>{drag=[e.clientX,e.clientY];c.setPointerCapture(e.pointerId);};c.onpointermove=e=>{if(drag){yaw+=(e.clientX-drag[0])*.008;pitch=Math.max(-1.3,Math.min(1.3,pitch+(e.clientY-drag[1])*.008));drag=[e.clientX,e.clientY];}};c.onpointerup=()=>drag=null;c.onwheel=e=>{e.preventDefault();zoom=Math.max(.2,Math.min(4,zoom*Math.exp(-e.deltaY*.001)));};requestAnimationFrame(draw);
</script></html>'''
    html = html.replace('</style>', 'body{overflow-x:hidden}canvas{width:100%;height:calc(100vh - 190px);min-height:240px}footer{display:grid;grid-template-columns:auto minmax(60px,1fr) auto;gap:10px;align-items:center}input{width:100%;min-width:0}#frame{margin-left:0;font-size:13px}.hint{grid-column:1/-1;margin-top:0}</style>')
    html = html.replace('requestAnimationFrame(draw);\n</script>', "addEventListener('message',e=>{if(e.data && e.data.type==='frame'){playing=false;seek.value=Math.max(0,Math.min(data.joints.length-1,Number(e.data.frame)||0));}});requestAnimationFrame(draw);\n</script>")
    import html as html_module
    html = html.replace('SMPL-X skeleton',html_module.escape(label))
    if hint is not None:
        html = html.replace('Research prototype: static person ROI. Foot-lock optimizer and Manny retargeting are not applied.',html_module.escape(hint))
    path.write_text(html.replace('PAYLOAD',payload),encoding='utf-8')


def write_pair_preview(path,frames,fps):
    html = '''<!doctype html><html lang="ja"><meta charset="utf-8"><title>Movie2Anim · Two-person verification</title>
<style>body{margin:0;background:#101622;color:#e5edf8;font:15px system-ui}header{padding:18px 24px}h1{font-size:23px}main{display:flex;height:78vh}iframe{width:50%;border:1px solid #344058}button{padding:8px 16px;background:#4778ef;color:white;border:0;border-radius:5px}input{width:60%}p{color:#b6c5da}</style>
<header><h1>Two-person capture / independent ROIs</h1><p>人物ごとに独立推定・原点化した比較表示です。2人の距離・接触・相互作用は再現していません。</p>
<button id="play">Play both</button> <input id="seek" type="range" min="0" max="MAXFRAME" value="0"><span id="label"></span></header>
<main><iframe src="person_01/preview.html"></iframe><iframe src="person_02/preview.html"></iframe></main>
<script>let playing=false,start=0;const s=document.getElementById('seek'),btn=document.getElementById('play');function sync(){document.querySelectorAll('iframe').forEach(f=>f.contentWindow.postMessage({type:'frame',frame:Number(s.value)},'*'));document.getElementById('label').textContent=` ${Number(s.value)+1} / FRAMECOUNT`;}
btn.onclick=()=>{playing=!playing;start=performance.now()-Number(s.value)/FPS*1000;btn.textContent=playing?'Pause':'Play both';};s.oninput=()=>{playing=false;btn.textContent='Play both';sync();};function tick(t){if(playing){s.value=Math.floor((t-start)/1000*FPS)%FRAMECOUNT;sync();}requestAnimationFrame(tick);}requestAnimationFrame(tick);</script></html>'''
    html = html.replace('</style>','*{box-sizing:border-box}body{overflow:hidden}main{height:calc(100vh - 164px)}iframe{min-width:0}</style>')
    path.write_text(html.replace('MAXFRAME',str(frames-1)).replace('FRAMECOUNT',str(frames)).replace('FPS',str(fps)),encoding='utf-8')
