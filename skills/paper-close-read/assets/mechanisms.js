/* Deterministic explanatory scenes. Illustrative geometry, never fitted paper data. */
(()=>{'use strict';
const palette={ink:'#454039',muted:'#9b9081',rose:'#cf5267',green:'#52836b',blue:'#568ba1',gold:'#d3a35b',line:'#ded8ca',bg:'#fcfbf7'};
const players=[];window.mechanismPlayers=players;
document.querySelectorAll('[data-mechanism]').forEach(el=>{
 const cfg=JSON.parse(el.dataset.mechanism),canvas=el.querySelector('canvas'),ctx=canvas.getContext('2d');
 const W=900,H=440,dpr=Math.max(1,canvas.getBoundingClientRect().width/W)*Math.min(devicePixelRatio||1,2);canvas.width=W*dpr;canvas.height=H*dpr;ctx.scale(dpr,dpr);
 let progress=0,running=false,last=0,raf=0;const duration=14000,slider=el.querySelector('[data-scrub]'),play=el.querySelector('[data-play]'),caption=el.querySelector('.motion-caption'),counter=el.querySelector('[data-step-label]'),speed=el.querySelector('[data-speed]');
 const mix=(a,b,t)=>a+(b-a)*Math.max(0,Math.min(1,t));const phase=(a,b)=>Math.max(0,Math.min(1,(progress-a)/(b-a)));const P=palette;
 function line(x,y,x2,y2,color=P.line,width=2,dash=[]){ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=width;ctx.setLineDash(dash);ctx.moveTo(x,y);ctx.lineTo(x2,y2);ctx.stroke();ctx.setLineDash([]);}
 function text(s,x,y,size=18,color=P.ink,align='left',bold=false){ctx.font=(bold?'600 ':'')+size+'px "Microsoft YaHei", "Segoe UI", sans-serif';ctx.fillStyle=color;ctx.textAlign=align;ctx.textBaseline='middle';ctx.fillText(s,x,y);}
 function circle(x,y,r,fill,stroke=null,width=2){ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);if(fill){ctx.fillStyle=fill;ctx.fill();}if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=width;ctx.stroke();}}
 function rect(x,y,w,h,fill,stroke=null,r=8){ctx.beginPath();ctx.roundRect(x,y,w,h,r);if(fill){ctx.fillStyle=fill;ctx.fill();}if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1;ctx.stroke();}}
 function arrow(x,y,x2,y2,color=P.muted,width=2){line(x,y,x2,y2,color,width);const a=Math.atan2(y2-y,x2-x);line(x2,y2,x2-9*Math.cos(a-.45),y2-9*Math.sin(a-.45),color,width);line(x2,y2,x2-9*Math.cos(a+.45),y2-9*Math.sin(a+.45),color,width);}
 function title(s,x=35,y=33){text(s,x,y,18,P.ink,'left',true);}
 function star(x,y,color=P.rose){line(x-7,y,x+7,y,color,3);line(x,y-7,x,y+7,color,3);}
 function grid(x,y,w,h){rect(x,y,w,h,'#f4f5ed',P.line);for(let a=x+40;a<x+w;a+=40)line(a,y,a,y+h,'#e9eadf',1);for(let a=y+40;a<y+h;a+=40)line(x,a,x+w,a,'#e9eadf',1);}
 const route=[[70,340],[140,300],[160,240],[230,215],[275,165],[350,140],[420,90]];
 const lengths=route.slice(1).map((p,i)=>Math.hypot(p[0]-route[i][0],p[1]-route[i][1]));
 function atRoute(t){let distance=Math.max(0,Math.min(1,t))*lengths.reduce((a,b)=>a+b,0);for(let i=0;i<lengths.length;i++){if(distance<=lengths[i]||i===lengths.length-1){const q=distance/lengths[i];return [mix(route[i][0],route[i+1][0],q),mix(route[i][1],route[i+1][1],q)];}distance-=lengths[i];}}
 function path(){for(let i=1;i<route.length;i++)line(...route[i-1],...route[i],P.rose,4);}
 function spatial(){
  title('同一个中心，不同轮次的位置');grid(35,62,425,325);path();
  const centre=[265,235],locations=[[220,223],[340,295],[305,160]],round=Math.min(2,Math.floor(progress*3)),q=progress===1?1:(progress*3)%1;
  circle(...centre,88,null,'#b8cebf',2);star(...centre,P.green);text('活动中心 s',centre[0]+12,centre[1]+22,15,P.green);
  const prev=round?locations[round-1]:centre;const pos=[mix(prev[0],locations[round][0],Math.min(1,q*2)),mix(prev[1],locations[round][1],Math.min(1,q*2))];
  for(let i=0;i<round;i++){circle(...locations[i],5,'#b8c6bd');line(...centre,...locations[i],'#bdcabe',1,[4,4]);}
  line(...centre,...pos,P.green,1,[4,4]);circle(...pos,9,P.blue);text('当次位置 u',pos[0]+14,pos[1]-12,15,P.blue);
  const observer=atRoute(Math.min(1,q*1.5));circle(...observer,7,P.rose);text('搜索路线 X',55,365,15,P.rose);
  title('观测记录：看到才记坐标',515,65);const seen=[true,false,true];
  ['轮次','是否遇到 y','坐标 u'].forEach((s,i)=>text(s,[530,635,765][i],112,16,P.muted));
  for(let i=0;i<3;i++){rect(510,138+i*59,350,46,i===round?'#eef4ef':'#f6f3ed');text('第 '+(i+1)+' 轮',530,160+i*59,17);const done=i<round||(i===round&&q>.55)||progress===1;text(done?(seen[i]?'1':'0'):'…',670,160+i*59,20,done&&seen[i]?P.green:P.muted);text(done?(seen[i]?'记录位置':'未观测'):'等待搜索',755,160+i*59,16,seen[i]?P.green:P.muted);}
  text('s → u → y',685,350,27,P.green,'center',true);text('移动过程连接位置，路线决定发现机会',685,391,17,P.muted,'center');
 }
 function hazard(){
  title('沿路线累积，再换成概率');grid(35,62,425,325);path();const animal=[265,210];circle(...animal,10,P.blue);text('个体位置 u',282,215,16,P.blue);
  const count=18,upto=Math.floor(progress*count);let total=0;const weights=[];
  for(let i=0;i<count;i++){const pos=atRoute(i/(count-1));const d=Math.hypot(pos[0]-animal[0],pos[1]-animal[1]);const h=.38*Math.exp(-d*d/(2*85*85));weights.push(h);const active=i<=upto;if(active)total+=h;circle(...pos,4,active?P.rose:'#d7c9c1');if(i===Math.min(upto,count-1))line(...pos,...animal,P.gold,2,[5,4]);}
  const marker=atRoute(progress);circle(...marker,8,P.rose);
  title('每一小段贡献一点强度',505,72);for(let i=0;i<count;i++){const h=weights[i]*210;rect(510+i*18,205-h,11,h,i<=upto?P.rose:'#e6e1d8',null,2);}line(503,207,847,207);text('沿路线的小段',680,233,16,P.muted,'center');
  const prob=1-Math.exp(-total);text('累计强度 H',510,282,17);rect(650,269,200,24,'#ece8df');rect(650,269,Math.min(total/4,1)*200,24,P.gold);text('遭遇概率 p',510,330,17);rect(650,318,200,24,'#ece8df');rect(650,318,prob*200,24,P.green);text('p = 1 − exp(−H)',680,385,24,P.green,'center',true);text('0',650,358,14,P.muted);text('1',850,358,14,P.muted,'right');
 }
 function augmentation(){
  title('先留空位，再判断哪些行是真实成员');const rows=8,selected=[1,1,1,1,0,1,0,0];
  text('固定长度的候选名单',55,74,17,P.muted);text('三轮遭遇史',255,74,17,P.muted);text('成员开关 w',455,74,17,P.muted);
  for(let i=0;i<rows;i++){const y=111+i*36,known=i<3,revealed=known||progress>.22; if(!revealed)continue;rect(45,y-14,485,30,known?'#f4f2ec':'#eef3ee');text(known?'已观察 '+(i+1):'新增候选 '+(i-2),60,y,16);text(known?['1  0  1','0  1  0','1  1  0'][i]:'0  0  0',265,y,18,known?P.ink:P.muted);const decided=known||progress>.4+(i-3)*.06;const value=decided?selected[i]:null;rect(462,y-11,42,23,value===1?P.green:value===0?'#c4bdb1':'#e2dcd0',null,11);text(value===null?'?':String(value),483,y,16,'white','center',true);}
  arrow(560,220,625,220,P.green,3);rect(650,123,205,195,'#f3f6ef',P.line);text('N = Σ w',752,168,30,P.green,'center',true);
  const counted=selected.reduce((n,v,i)=>n+(i<3||progress>.4+(i-3)*.06?v:0),0);text(progress>=.75?'本次示意：N = 5':'当前确定：'+counted,752,230,22,P.ink,'center');text('全零：漏检或占位',752,285,16,P.muted,'center');text('M = 8：计算表长度',60,421,16,P.muted);text('5 与 8 仅用于演示',752,361,15,P.muted,'center');
 }
 function boundary(){
  title('中心在边界附近，位置会进出调查范围');grid(35,65,490,320);ctx.fillStyle='#e6eee5';ctx.fillRect(110,110,280,225);ctx.strokeStyle=P.green;ctx.lineWidth=2;ctx.strokeRect(110,110,280,225);text('调查样地 𝒳',130,135,17,P.green);
  const centre=[370,235],pos=[390-60*Math.sin(progress*1.5*Math.PI),235+45*Math.sin(progress*2*Math.PI)],inside=pos[0]<=390&&pos[0]>=110&&pos[1]<=335&&pos[1]>=110;
  ctx.beginPath();ctx.ellipse(...centre,86,58,0,0,Math.PI*2);ctx.setLineDash([5,5]);ctx.strokeStyle='#a5b7a2';ctx.stroke();ctx.setLineDash([]);star(...centre,P.green);circle(...pos,10,inside?P.blue:P.muted);line(...centre,...pos,P.muted,1,[3,4]);text('活动中心 s',centre[0]-90,centre[1]+23,15,P.green);text('状态空间 S（含缓冲）',55,370,16,P.muted);
  title('记录规则看的是当次位置',565,90);rect(560,135,300,75,inside?'#edf5ed':'#f1ede8');text(inside?'在样地内：有机会记录':'在样地外：本轮 p = 0',710,174,20,inside?P.green:P.muted,'center',true);
  text('中心 s 不随每次出入而改变',560,255,18);text('N 与面积使用同一个 S',560,300,18);text('D = N / area(S)',560,350,25,P.green,'left',true);
 }
 function vessel(){
  title('离体血管：钙进入减少，平滑肌张力下降');const blocked=phase(.2,.72),radius=mix(43,75,blocked);
  text('血管横截面',236,87,18,P.muted,'center');circle(236,230,105,'#eed7cc');circle(236,230,radius,'#fffdf6',P.rose,3);
  for(let i=0;i<12;i++){const a=i/12*Math.PI*2;circle(236+86*Math.cos(a),230+86*Math.sin(a),7,'#cf987e');}
  text('管腔',236,230,20,P.rose,'center');text(blocked>.7?'肌肉放松 → 管腔变宽':'肌肉收缩 → 管腔较窄',236,375,19,P.ink,'center');
  title('看钙通道这一环',488,85);rect(488,138,345,130,'#f1eee7',P.line);line(550,155,550,250,P.rose,6);line(600,155,600,250,P.rose,6);
  const flux=1-.75*blocked;for(let i=0;i<7;i++){const t=(progress*4+i/7)%1,x=500+t*285;const pass=i/7<flux;if(pass||x<550)circle(x,178+(i%3)*29,6,P.blue);}
  text('Ca²⁺',498,120,18,P.blue);text('通道',576,290,16,P.muted,'center');if(blocked>.2){line(547,205,602,205,P.rose,5);text('进入减少',706,300,18,P.rose,'center');}
  text('钙电流↓ → 张力↓ → 舒张',660,349,21,P.green,'center',true);text('整体血压还受肾脏、激素和其他血管调节',450,413,17,P.muted,'center');
 }
 function cholesterol(){
  title('胆固醇的“出口”变少，细胞内逐渐堆积');const suppress=phase(.18,.7);
  function cell(cx,changed){circle(cx,235,120,changed?'#faf1e2':'#edf3ed',changed?P.gold:P.green,3);circle(cx-37,244,29,'#ded6c8');text('巨噬细胞',cx,391,17,P.muted,'center');const gateY=195;rect(cx+107,gateY,25,74,'#fffdf7');const open=changed?1-suppress:1;line(cx+117,gateY,cx+117,gateY+74*(1-open),changed?P.rose:P.green,6);text('ABCA1',cx+116,gateY-17,17,changed?P.rose:P.green,'center');arrow(cx+130,231,cx+187,231,changed?P.rose:P.green,3);
   const dots=changed?8+Math.floor(suppress*20):8;for(let i=0;i<dots;i++){const a=i*2.399,r=35+((i*23)%60);circle(cx+Math.cos(a)*r,235+Math.sin(a)*r,5,P.gold);}
   const efflux=changed?1-.8*suppress:1;for(let i=0;i<4;i++){if(i/4<efflux){const t=(progress*3+i/4)%1;circle(cx+120+t*70,230+(i%2)*12,5,P.gold);}}
  }
  text('正常外排',210,83,21,P.green,'center',true);text('ABCA1表达受抑',660,83,21,P.rose,'center',true);cell(190,false);cell(635,true);text('不断运出',370,297,16,P.green,'center');text(suppress>.6?'外排减少':'外排通路',817,297,16,P.rose,'center');
  text('黄色小点 = 胆固醇；右侧演示DBP实验提出的细胞机制',450,427,16,P.muted,'center');
 }
 function oxidative(){
  title('按时间追踪：氧化压力 → 细胞器变化 → 损伤');const stress=phase(.05,.4),damage=phase(.4,.8),end=phase(.8,1);
  ctx.beginPath();ctx.ellipse(280,235,218,145,0,0,Math.PI*2);ctx.fillStyle='#f0f4ed';ctx.fill();ctx.strokeStyle=P.green;ctx.lineWidth=3;ctx.stroke();circle(212,245,43,'#e0d8ce');text('细胞核',212,245,17,P.ink,'center');
  for(let i=0;i<18*stress;i++){const a=i*2.399+progress,r=90+(i%4)*18;circle(280+Math.cos(a)*r,235+Math.sin(a)*r*.72,4,P.rose);}
  ctx.save();ctx.translate(365,217);ctx.rotate(-.4);rect(-52,-24,104,48,'#f5d9ba',P.gold,24);for(let i=0;i<5;i++)line(-34+i*15,-13,-27+i*15,13,P.gold,3);ctx.restore();text('线粒体',365,270,16,P.gold,'center');
  for(let i=0;i<Math.floor(1+stress*3);i++){const x=150+i*65,y=145;circle(x,y,15,'#e0e7d3',P.green,1);circle(x,y,11,null,P.green,1);}
  text('自噬相关囊泡',248,113,15,P.green,'center');text('ROS',112,210,15,P.rose);circle(310,319,21,'#ece0ea',damage>.5?P.rose:'#a785aa',damage>.5?3:1);text('溶酶体',310,358,15,'#96769c','center');
  if(damage>.2){for(let i=0;i<5;i++){const t=(progress*3+i/5)%1;circle(365+45+t*60,215+(i-2)*13,4,P.rose);}}
  if(end>0){for(let i=0;i<6;i++){const a=i*Math.PI/3;circle(280+225*Math.cos(a),235+150*Math.sin(a),6+end*5,'#ead6d2');}}
  const stages=['MEHP处理后：ROS等反应变化','早期：自噬相关变化','随后：膜通透性与凋亡增加'];
  stages.forEach((s,i)=>{const active=progress>=i/3;rect(545,105+i*91,325,62,active?'#f7eee5':'#f3f1ea',active?P.gold:P.line);text(String(i+1).padStart(2,'0'),560,135+i*91,17,active?P.rose:P.muted);text(s,593,135+i*91,16,active?P.ink:P.muted);if(i<2)arrow(710,172+i*91,710,189+i*91,P.muted);});
  text('整合相关细胞实验：用先后顺序与通路干预追查机制',450,420,17,P.muted,'center');
 }
 function molecular_sampling(){
  title('总体有A也有B，每一小管却未必都有');
  rect(35,85,205,245,'#eef3ee',P.green,24);text('提取液：A / B',137,65,19,P.green,'center',true);
  const types=['A','B','A','B','A','B','A','B'];
  types.forEach((a,i)=>{if(i<4)return;const x=76+(i%3)*58,y=126+Math.floor(i/3)*67;circle(x,y,11,a==='A'?P.blue:P.rose);text(a,x,y,13,'white','center',true);});
  const contents=[['A','B'],['A'],['B'],[]],labels=['两者都有','只有A','只有B','没有靶分子'];
  for(let j=0;j<4;j++){
   const x=315+j*145;rect(x,140,95,144,'#fffdf8',P.line,18);text('第'+(j+1)+'管',x+47,110,18,P.ink,'center');
   const t=phase(j*.09,.48+j*.09);
   contents[j].forEach((a,k)=>{const index=j===0?k:j+1;const px=mix(76+(index%3)*58,x+32+k*32,t),py=mix(126+Math.floor(index/3)*67,218,t);circle(px,py,11,a==='A'?P.blue:P.rose);text(a,px,py,13,'white','center',true);});
   if(progress>.72){contents[j].forEach(a=>line(x+20,a==='A'?323:347,x+75,a==='A'?323:347,a==='A'?P.blue:P.rose,6));text(labels[j],x+47,385,16,contents[j].length===2?P.green:P.muted,'center');}
  }
  if(progress<.72)text('分子进入反应管：固定示例，非结果比例',562,359,19,P.muted,'center');
  text('A：蓝色  B：玫瑰色；同体积取样 ≠ 相同分子组成',450,420,17,P.ink,'center');
 }
 function pcr_slippage(){
  title('早期复制少了一格，后续还会继续复制这个版本');
  function strand(x,y,short){for(let k=0;k<(short?4:5);k++){rect(x+k*18,y,15,16,short?P.rose:P.blue,null,2);} }
  text('起始模板：5个重复单位',50,89,18);strand(66,116,false);
  arrow(188,125,270,125,P.muted,3);text('首轮复制',227,160,17,P.muted,'center');
  strand(310,103,false);if(progress>.12)strand(310,179,true);
  text('正确长度',430,110,17,P.blue);if(progress>.12)text('滑移：少一个单位',430,186,17,P.rose);
  const count=1+Math.floor(phase(.2,.92)*7);
  for(let k=0;k<count;k++){const y=265+(k%4)*27,x=315+Math.floor(k/4)*112;strand(x,y,false);if(progress>.2)strand(x+300,y,true);}
  arrow(420,131,420,240,P.blue,2);if(progress>.2)arrow(352,205,652,240,P.rose,2);
  text('正确版本的后代',395,389,18,P.blue,'center');text('错误版本的后代',695,389,18,P.rose,'center');
  text('教学复制树：示意早期错误可被放大，不表示测得的分子数量或发生率',450,423,16,P.muted,'center');
 }
 function replicate_consensus(){
  title('每加一管独立证据，重新看整个观察模式');
  const seqs=[['AB','A','B','—','—','—','—'],['A','A','A','A','A','A','A'],['A','A','AC','A','A','A','A']];
  const names=['A、B各自复现','持续只见A','C只出现一次'];
  const n=Math.min(7,1+Math.floor(progress*7));
  for(let row=0;row<3;row++){
   const y=115+row*97;text(names[row],35,y+19,17,P.ink); 
   for(let j=0;j<7;j++){const x=245+j*82,shown=j<n,stop=row===0&&j>=3;rect(x,y,67,47,shown&&!stop?'#edf3ee':'#f2efe8',P.line);text(shown?(stop?'停':seqs[row][j]):'·',x+33,y+24,19,row===2&&j===2?P.rose:P.ink,'center',true);if(row===0)text(String(j+1),x+33,87,15,P.muted,'center');}
  }
  text(n<3?'先取得3次阳性PCR，再看证据是否清楚':n<7?'第一行证据已清楚；另外两行还需继续观察':'仅A持续出现与偶见C属于不同证据模式；含混时继续复核',450,400,18,P.green,'center',true);
  text('每列是一管独立起始的阳性PCR；固定教学例子，不执行项目基因型裁定',450,429,15,P.muted,'center');
 }
 function argument_map(){
  const v=cfg.visual,ns=v.nodes,stage=Math.min(cfg.stages.length-1,Math.floor(progress*cfg.stages.length));
  title(cfg.title);const positions=ns.map((n,i)=>({x:45+(i%3)*288,y:ns.length>3?85+Math.floor(i/3)*170:135,w:235,h:108}));
  const labels={supports:'支持',rebuts:'反驳',defines:'界定',precedes:'先后',compares:'对照',causes:'因果',interprets:'解释'};
  for(const edge of v.edges){const ai=ns.findIndex(n=>n.id===edge.from),bi=ns.findIndex(n=>n.id===edge.to),a=positions[ai],b=positions[bi],active=ns[ai].stage<=stage&&ns[bi].stage<=stage;const color=active?(edge.relation==='rebuts'?P.rose:P.green):'#e4dfd4';
   if(Math.abs(a.y-b.y)<1){const right=b.x>a.x;arrow(right?a.x+a.w:a.x,a.y+54,right?b.x:b.x+b.w,b.y+54,color,2);text(labels[edge.relation],(a.x+b.x+a.w)/2,a.y+31,13,color,'center');}
   else{arrow(a.x+a.w/2,a.y+a.h,b.x+b.w/2,b.y,color,2);text(labels[edge.relation],(a.x+b.x+a.w)/2+20,(a.y+a.h+b.y)/2,13,color);}}
  ns.forEach((n,i)=>{const q=positions[i],active=n.stage<=stage;rect(q.x,q.y,q.w,q.h,active?'#edf3ed':'#f0ede6',active?'#a9bfad':P.line);text(n.label,q.x+15,q.y+23,17,active?P.green:P.muted,'left',true);n.lines.forEach((l,j)=>text(l,q.x+15,q.y+51+j*22,16,active?P.ink:'#ada69b'));});
  text('箭头按所标关系阅读；亮起表示当前推理步骤',450,410,16,P.muted,'center');
 }
 function evidence_coding(){
  const v=cfg.visual,stage=Math.min(cfg.stages.length-1,Math.floor(progress*cfg.stages.length));title(cfg.title);
  const xs=[40,335,630],names=['材料片段','关注点 / 编码','主题 / 解释'];names.forEach((n,i)=>text(n,xs[i],82,18,P.muted));
  v.nodes.slice(0,3).forEach((n,i)=>{const active=stage>=n.stage;rect(xs[i],125,230,174,active?'#edf3ed':'#f1eee7',P.line);text(n.label,xs[i]+15,157,17,active?P.green:P.muted,'left',true);n.lines.forEach((l,j)=>text(l,xs[i]+15,194+j*28,16,active?P.ink:P.muted));if(i<2){const q=phase(i*.33,(i+1)*.33);arrow(xs[i]+240,218,xs[i+1]-15,218,P.line);text('解释',xs[i]+263,194,12,P.muted,'center');circle(mix(xs[i]+242,xs[i+1]-15,q),218,6,q>0?P.gold:P.line);}});
  text('材料支持解释：这里展示阅读重建，不冒充作者逐条编码记录',450,372,17,P.muted,'center');
 }
 function repeated_measures(){
  const v=cfg.visual;title(cfg.title);line(85,215,815,215,P.line,3);const points=[120,450,780],labels=['前一次 T1','两次之间','这一次 T2'];
  points.forEach((x,i)=>{circle(x,215,9,progress>=i/3?P.blue:P.line);text(labels[i],x,175,18,P.muted,'center');});
  const notes=[v.before,v.interval,v.after];notes.forEach((n,i)=>{rect(points[i]-100,260,200,64,progress>=i/3?'#edf3ed':'#f2efe8',P.line);text(n,points[i],292,16,progress>=i/3?P.ink:P.muted,'center');});
  arrow(145,115,745,115,P.blue,2);circle(mix(145,745,progress),115,7,P.rose);text('时间推进；区间里的使用由T2回顾报告',450,80,17,P.muted,'center');
  text(v.meaning,450,385,18,P.green,'center',true);text('演示记录与比较顺序，不模拟论文效应大小',450,422,16,P.muted,'center');
 }
 function source_timeline(){
  const v=cfg.visual,step=Math.min(cfg.stages.length-1,Math.floor(progress*cfg.stages.length));title(cfg.title);
  v.layers.forEach((x,i)=>{const active=step>=i,y=105+i*106;line(204,y,830,y,P.line,2);circle(225,y,9,active?P.blue:P.line);text(x.label,35,y-10,19,active?P.green:P.muted,'left',true);text(x.date,35,y+20,16,P.muted);rect(260,y-29,570,59,active?'#edf3ed':'#f1eee7',P.line);text(x.detail,280,y,18,active?P.ink:P.muted);if(i<2){arrow(225,y+14,225,y+90,P.line,2);circle(225,mix(y+14,y+90,phase(i/3,(i+1)/3)),5,active?P.gold:P.line);}});
  text('依次核对事件、记录和解释；行间连接表示取材关系',450,414,16,P.muted,'center');
 }
 function communication(){
  const v=cfg.visual,step=Math.min(v.steps.length-1,Math.floor(progress*v.steps.length)),st=v.steps[step];title(cfg.title);
  const ps=[{x:130,y:160},{x:450,y:160},{x:770,y:160}];
  v.nodes.forEach((n,i)=>{circle(ps[i].x,ps[i].y,37,'#edf3ed',P.green);text((st.labels||{})[n.id]||n.label,ps[i].x,ps[i].y+65,18,P.ink,'center',true);});
  st.channels.forEach((ch,i)=>{const a=ps[v.nodes.findIndex(n=>n.id===ch.from)],b=ps[v.nodes.findIndex(n=>n.id===ch.to)],q=(progress*v.steps.length)%1,back=b.x<a.x,y=ch.mode==='overhears'||ch.mode==='letter'?99:160,color=ch.mode==='overhears'?P.gold:ch.mode==='letter'?P.rose:P.blue;
   arrow(a.x+(back?-45:45),y,b.x+(back?45:-45),y,color,2);circle(mix(a.x+(back?-45:45),b.x+(back?45:-45),progress===1?1:q),y,6,color);text({speaks:'说给对方听',overhears:'旁边听到',letter:'写信确认'}[ch.mode],(a.x+b.x)/2,y-20,15,color,'center');});
  rect(60,280,780,105,'#f6f2e8',P.line);text(st.message,85,309,19,P.ink);text(st.interpretation,85,353,18,P.green);text('位置与通道为教学示意；人物判断随所获信息变化',450,416,16,P.muted,'center');
 }
 function text_focus(){
  const v=cfg.visual,step=Math.min(v.focuses.length-1,Math.floor(progress*v.focuses.length)),focus=v.focuses[step];title(cfg.title);text(v.attribution,42,80,16,P.muted);
  const words=v.quote.split(' ');let x=58,y=154;ctx.font='24px Georgia';
  const start=v.quote.indexOf(focus.text),end=start+focus.text.length;let offset=0;
  words.forEach(word=>{ctx.font='24px Georgia';const width=ctx.measureText(word+' ').width;if(x+width>842){x=58;y+=46;}const on=offset<end&&offset+word.length>start;if(on)rect(x-3,y-20,width,38,'#f6dfad',null,3);ctx.font='24px Georgia';ctx.fillStyle=P.ink;ctx.textAlign='left';ctx.textBaseline='middle';ctx.fillText(word,x,y);x+=width;offset+=word.length+1;});
  line(58,275,842,275,P.line,1);text('抓住措辞，再说明它怎样支持解读',58,308,17,P.muted);text(focus.meaning,58,352,19,P.green,'left',true);text('高亮仅用于细读，英文来自所链接的论文引文',450,415,16,P.muted,'center');
 }


 function edna_capture(){
  title('水里的碎片，怎样变成物种名单？');rect(40,92,310,265,'#e8f2f5',P.blue);text('混合水样',195,72,18,P.blue,'center');
  const collected=phase(.1,.46),read=phase(.48,.98);line(410,100,410,346,P.green,10);text('滤膜',410,375,18,P.green,'center');arrow(350,218,391,218,P.blue);
  for(let i=0;i<24;i++){const y=125+(i*37)%190,x=70+(i*41)%230,move=collected>i/24?phase(i/70,.46):0;const tx=mix(x,405,move);rect(tx,y,13,5,i%3===0?P.rose:P.gold,null,2);}
  text('细胞残片 / 颗粒结合DNA',195,395,17,P.muted,'center');arrow(440,218,520,218,P.green);
  rect(545,111,300,220,'#fffdf7',P.line);text('提取 → 扩增 → 读序列',695,143,19,P.ink,'center',true);
  ['片段 A → 参考库 → 鱼种 A','片段 B → 参考库 → 鱼种 B','无法唯一匹配 → 暂不报种'].forEach((a,i)=>{text(read>(i*.28)?a:'等待读取',565,195+i*48,17,read>(i*.28)?P.green:P.muted);});
  text('示意颗粒数不代表鱼的条数；参考库决定能否叫出名字',450,429,16,P.muted,'center');
 }
 function edna_decay(){
  const v=cfg.visual,titleText='信号降到检测线以下，过线时间取决于起点和速率';title(titleText);
  const x=85,y=355,w=720,h=230,max=v.maximum,days=v.days;line(x,y,x+w,y,P.muted);line(x,y,x,y-h-15,P.muted);
  text('浓度（分子 / 400 ml）',85,84,16,P.muted);text('时间（天）',806,397,16,P.muted,'right');
  for(let i=0;i<=days;i++){text(String(i),x+i/days*w,y+22,14,P.muted,'center');}
  const yy=y-v.threshold/max*h;line(x,yy,x+w,yy,P.rose,2,[6,5]);text('检测线 '+v.threshold,x+w,yy-16,15,P.rose,'right');
  v.curves.forEach((c,j)=>{const color=j?P.green:P.blue;ctx.beginPath();for(let k=0;k<=160;k++){const t=k/160*days,pY=y-c.initial*Math.exp(-c.rate*t)/max*h;k?ctx.lineTo(x+t/days*w,pY):ctx.moveTo(x,pY);}ctx.strokeStyle=color;ctx.lineWidth=2;ctx.stroke();
   const t=progress*days,N=c.initial*Math.exp(-c.rate*t);circle(x+t/days*w,y-N/max*h,7,color);text(c.label+'：'+N.toFixed(1),115+j*335,112,18,color,'left',true);});
  line(x+progress*w,135,x+progress*w,y,P.gold,1,[3,3]);text('曲线按所列模型参数重画；不是新增测量点',450,428,16,P.muted,'center');
 }
 function qpcr_probe(){
  title('引物启动复制，探针切开后报告荧光');line(70,220,830,220,P.blue,6);text('目标模板（位置为示意）',75,263,18,P.blue);
  const ext=phase(.25,.8);rect(90,185,110,16,P.green);text('引物 3′ →',90,160,18,P.green);line(200,193,mix(200,790,ext),193,P.green,6);
  const split=phase(.54,.82);rect(455,185,split>0?70:145,16,P.gold);if(split>0)rect(mix(530,635,split),mix(185,122,split),70,16,P.gold);text('探针',525,155,18,P.gold,'center');circle(465,173,10,P.rose);circle(mix(585,690,split),mix(173,110,split),10,P.muted);
  if(split>.15){for(let k=0;k<8;k++){const a=k*Math.PI/4;line(465+17*Math.cos(a),173+17*Math.sin(a),465+(20+split*14)*Math.cos(a),173+(20+split*14)*Math.sin(a),P.rose,2);}}
  text(split>.7?'报告基团与淬灭基团分离 → 荧光增加':split>.05?'探针逐步切开 → 荧光增强':'探针完整时：荧光受淬灭',450,330,22,split>.7?P.rose:P.muted,'center',true);
  text('每轮产物增加，荧光累积；较早越线对应较小Ct',450,390,18,P.green,'center');
 }
 function primer_specificity(){
  title('把辨认放在探针端，还是扩增入口？');const q=phase(.2,.95);
  ['主要靠探针区别','引物区增加有效区别'].forEach((label,j)=>{const y=160+j*160;text(label,45,y-75,20,j?P.green:P.rose,'left',true);line(50,y,410,y,P.blue,5);text('近缘非目标模板',55,y+34,16,P.muted);
   rect(75,y-27,85,13,P.green);text('引物',75,y-48,15,P.green);rect(270,y-27,85,13,P.gold);text('探针',270,y-48,15,P.gold);
   if(j){star(151,y-20,P.rose);text('3′附近错配',180,y+35,16,P.rose);line(160,y-20,180,y-20,P.rose,4);}else{star(308,y-20,P.rose);line(160,y-20,mix(160,402,q),y-20,P.green,4);}
   arrow(425,y,470,y,j?P.green:P.rose);const n=j?Math.floor(q*2):Math.floor(q*18);
   for(let k=0;k<n;k++)rect(490+(k%9)*32,y-25+Math.floor(k/9)*30,21,7,j?P.muted:P.rose,null,2);
   text(j?'减少非目标进入扩增':'非目标仍可能扩增、争用引物',490,y+48,18,j?P.green:P.rose);});
  text('原理示意：实际效果还受错配位置、种类和反应条件影响',450,430,16,P.muted,'center');
 }

 function gene_pool(){
  const initial=cfg.visual.initial,total=initial.reduce((a,b)=>a+b,0),f=(initial[0]+initial[1]/2)/total;
  const next=[f*f,2*f*(1-f),(1-f)*(1-f)],start=initial.map(n=>n/total),q=phase(.25,.5);
  title('看见显性性状，不代表 A 在基因库里变多');
  function bars(xs,x,label){text(label,x+120,91,19,P.ink,'center',true);['AA','Aa','aa'].forEach((s,i)=>{const y=151+i*66,color=[P.blue,P.green,P.gold][i];text(s,x,y,18,color);rect(x+43,y-12,170,25,'#ece8df');rect(x+43,y-12,170*xs[i],25,color);text((xs[i]*100).toFixed(1)+'%',x+224,y,17,P.ink);});}
  bars(start,40,'起始一代');bars(progress<.5?[0,0,0]:next,580,progress<.5?'下一代：等待结合':'随机交配后的期望比例');
  rect(350,109,174,225,'#f4f3eb',P.line);text('配子池',437,133,19,P.ink,'center',true);
  const count=20;for(let i=0;i<count;i++){const x=378+(i%4)*37,y=175+Math.floor(i/4)*27,t=phase(0,.35);circle(mix(i<count*f?110:230,x,t),mix(i<count*f?153:285,y,t),7,i<count*f?P.blue:P.gold);}
  text('A：'+(f*100).toFixed(1)+'%',437,326,17,P.blue,'center');text('a：'+((1-f)*100).toFixed(1)+'%',437,353,17,P.gold,'center');
  if(q>0){for(let i=0;i<6;i++){const t=(q+i/6)%1;circle(mix(523,607,t),mix(197,151+(i%3)*66,t),6,i%2?P.gold:P.blue);}arrow(525,235,574,235,P.green,2);}
  const phenotype=progress<.5?start[0]+start[1]:next[0]+next[1];text('显性表型占比：'+(phenotype*100).toFixed(1)+'%',450,395,20,P.green,'center',true);
  text(progress<.75?'配子中的A频率由 AA 与 Aa 一起决定':'再随机交配：配子比例相同，下一代期望仍为 '+next.map(n=>(n*100).toFixed(0)+'%').join(' : '),450,426,16,P.muted,'center');
 }
 function inference_regress(){
  title('把通行规则抄下来，与按规则走过去，是两种动作');
  rect(35,69,390,325,'#f5f1e9',P.line);rect(475,69,390,325,'#eef4ed',P.line);
  text('阿喀琉斯的办法：继续加前提',230,97,18,P.rose,'center',true);text('教学对照：实际使用推断规则',670,97,18,P.green,'center',true);
  const step=Math.min(3,Math.floor(progress*4)),ys=[155,205,255,305],labels=['A、B 已接受','C：若 A、B 则 Z','D：若 A、B、C 则 Z','E：若 A、B、C、D 则 Z'];
  labels.forEach((label,i)=>{if(i<=step){const t=i===step?Math.min(1,(progress*4-step)*3):1;rect(mix(84,61,t),ys[i]-18,330,35,i===step?'#f4dfdc':'#fffdfa',P.line);text(label,mix(97,74,t),ys[i],16,i===step?P.rose:P.ink);}});
  arrow(401,335,401,142,P.rose,2);text('还可再写一个条件',230,367,17,P.rose,'center');
  const t=phase(.1,.82);line(520,230,810,230,P.green,3);rect(621,185,77,91,'#fffdf6',P.green);text('使用',659,212,17,P.green,'center');text('规则',659,245,17,P.green,'center');
  for(let i=0;i<2;i++){const x=mix(520,756,Math.min(1,t*1.45-i*.15));circle(x,230+(i?21:-21),17,i?P.gold:P.blue);text(i?'B':'A',x,230+(i?21:-21),16,'white','center',true);}
  circle(811,230,24,t>.85?P.green:'#dce8d8');text('Z',811,230,22,t>.85?'white':P.green,'center',true);
  text(t>.85?'完成从前提到结论的这一步':'规则作为行动：不再要求先抄一句',670,338,16,P.green,'center');text('对照帮助分清命题与推断动作，不替原文给出最终解答',450,424,16,P.muted,'center');
 }
 const scenes={inference_regress,gene_pool,edna_capture,edna_decay,qpcr_probe,primer_specificity,source_timeline,communication,text_focus,argument_map,evidence_coding,repeated_measures,spatial,hazard,augmentation,boundary,vessel,cholesterol,oxidative,molecular_sampling,pcr_slippage,replicate_consensus};
 function draw(){ctx.clearRect(0,0,W,H);ctx.fillStyle=P.bg;ctx.fillRect(0,0,W,H);(scenes[cfg.scene]||(()=>text('演示场景未定义',40,80)))();const step=Math.min(cfg.stages.length-1,Math.floor(progress*cfg.stages.length));caption.textContent=cfg.stages[step];counter.textContent=(step+1)+' / '+cfg.stages.length;slider.value=Math.round(progress*1000);el.dataset.progress=progress.toFixed(4);el.dataset.stage=step;}
 function pause(){running=false;cancelAnimationFrame(raf);play.textContent='播放演示';play.setAttribute('aria-pressed','false');el.dataset.playing='false';}
 function tick(now){if(!running)return;if(last)progress=Math.min(1,progress+(now-last)/duration*Number(speed.value));last=now;draw();if(progress>=1)pause();else raf=requestAnimationFrame(tick);}
 play.onclick=()=>{if(running){pause();return;}players.forEach(p=>p.pause());if(progress>=1)progress=0;running=true;last=0;play.textContent='暂停';play.setAttribute('aria-pressed','true');el.dataset.playing='true';raf=requestAnimationFrame(tick);};
 slider.oninput=()=>{pause();progress=Number(slider.value)/1000;draw();};
 el.querySelector('[data-prev]').onclick=()=>{pause();progress=Math.max(0,(Math.floor(progress*cfg.stages.length)-1)/cfg.stages.length);draw();};
 el.querySelector('[data-next]').onclick=()=>{pause();progress=Math.min(1,(Math.floor(progress*cfg.stages.length)+1)/cfg.stages.length);draw();};
 el.querySelector('[data-reset]').onclick=()=>{pause();progress=0;draw();};
 const player={el,pause,seek:n=>{pause();progress=Math.max(0,Math.min(1,n));draw();}};players.push(player);draw();
 function resizeCanvas(){const width=Math.max(W,Math.round(canvas.getBoundingClientRect().width*Math.min(devicePixelRatio||1,2)));const height=Math.round(width*H/W);if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;ctx.setTransform(width/W,0,0,height/H,0,0);draw();}}
 let resizeRaf=0;if('ResizeObserver'in window)new ResizeObserver(()=>{cancelAnimationFrame(resizeRaf);resizeRaf=requestAnimationFrame(resizeCanvas);}).observe(canvas);resizeCanvas();
 if('IntersectionObserver'in window)new IntersectionObserver(entries=>{if(!entries[0].isIntersecting)pause();},{threshold:0}).observe(el);
});
document.addEventListener('visibilitychange',()=>{if(document.hidden)players.forEach(p=>p.pause());});
document.addEventListener('click',e=>{if(e.target.closest('[data-route],a.evidence'))players.forEach(p=>p.pause());});
})();
