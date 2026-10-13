'use strict';
const $ = id => document.getElementById(id);
const descriptions = {
  'first-contact': '01 / Learn the terrain. Compare signals. Find a way to EVE.',
  'false-echo': '02 / A convincing first hint points the wrong way. Let new evidence challenge it.',
  'last-charge': '03 / Eight units of power. A long search ahead. Know when to recharge.'
};
let state = null, running = false, busy = false, epoch = 0, timer = null, entries = [];
const pct = n => `${(n * 100).toFixed(1)}%`;
const coord = c => c ? `[${c.join(', ')}]` : '—';
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json', 'X-Echo-Client': '1'}, body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The request failed.');
  return result;
}
function fail(error) {
  running = false; clearTimeout(timer); $('error').textContent = error.message; $('error').hidden = false; controls();
}
function controls() {
  const ended = state && state.outcome !== 'searching';
  $('play').disabled = !state || ended || busy;
  $('play').textContent = running ? 'Ⅱ Pause' : !state || state.actions === 0 ? '▶ Start search' : '▶ Resume';
  $('step').disabled = !state || ended || busy || running;
  $('reset').disabled = !state;
  $('download').disabled = !state;
}
async function reset() {
  const token = ++epoch;
  running = false; busy = false; clearTimeout(timer);
  $('error').hidden = true; entries = []; state = null; controls();
  $('description').textContent = descriptions[$('mission').value];
  try {
    const next = await api('/api/sessions', {mission: $('mission').value});
    if (token !== epoch) return;
    state = next; render();
  } catch (error) { if (token === epoch) fail(error); }
}
async function step() {
  if (busy || !state || state.outcome !== 'searching') return;
  const token = epoch;
  busy = true; controls();
  try {
    const next = await api('/api/step', {session: state.session, revision: state.revision});
    if (token !== epoch) return;
    state = next;
    if (state.latest) entries.unshift(state.latest);
    if (state.outcome !== 'searching') running = false;
    render();
  } catch (error) { if (token === epoch) fail(error); }
  finally {
    if (token === epoch) {
      busy = false; controls();
      if (running) timer = setTimeout(step, Number($('speed').value));
    }
  }
}
function svgElement(tag, attrs, text) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
  if (text !== undefined) el.textContent = text;
  return el;
}
function map() {
  const svg = $('map'), unit = 38, margin = 22;
  svg.replaceChildren();
  svg.setAttribute('viewBox', `0 0 ${state.width*unit+margin*2} ${state.height*unit+margin*2}`);
  const known = new Map(state.terrain.map(t => [t.cell.join(','), t.kind]));
  const peak = Math.max(...state.belief.map(c => c.probability));
  for (let x=0;x<state.width;x++) svg.append(svgElement('text', {x:margin+x*unit+18,y:12,fill:'#8b9386','text-anchor':'middle','font-size':8}, String(x).padStart(2,'0')));
  for (let y=0;y<state.height;y++) svg.append(svgElement('text', {x:8,y:margin+y*unit+21,fill:'#8b9386','text-anchor':'middle','font-size':8}, String(y).padStart(2,'0')));
  for (const tile of state.belief) {
    const [x,y]=tile.cell, kind=known.get(tile.cell.join(','));
    const group=svgElement('g', {});
    const rect=svgElement('rect', {x:margin+x*unit,y:margin+y*unit,width:35,height:35,rx:4,fill:kind==='#'?'#747c70':kind==='C'?'#a6b99a':kind==='.'?'#f1efe5':'#cbd0c1'});
    group.append(rect);
    if ($('heatmap').checked && kind !== '#' && tile.probability > 0) group.append(svgElement('rect', {x:margin+x*unit,y:margin+y*unit,width:35,height:35,rx:4,fill:'#c98539',opacity:.65*Math.sqrt(tile.probability/peak)}));
    if (kind === undefined) group.append(svgElement('circle',{cx:margin+x*unit+17.5,cy:margin+y*unit+17.5,r:1.3,fill:'#9aab96'}));
    if (kind === '#') group.append(svgElement('path',{d:`M${margin+x*unit+10},${margin+y*unit+11}l14,14m0,-14l-14,14`,stroke:'#98a08d','stroke-width':1.5}));
    if (kind === 'C') group.append(svgElement('text',{x:margin+x*unit+17.5,y:margin+y*unit+24,'text-anchor':'middle',fill:'#33533e','font-size':22},'ϟ'));
    group.append(svgElement('title',{},`${coord(tile.cell)} · ${kind==='#'?'obstacle':kind==='C'?'charger':kind==='.'?'observed':'unknown'} · probability ${pct(tile.probability)}`));
    svg.append(group);
  }
  svg.append(svgElement('polyline',{points:state.path.map(([x,y])=>`${margin+x*unit+17.5},${margin+y*unit+17.5}`).join(' '),fill:'none',stroke:'#ad663c','stroke-width':2.5,opacity:.65,'stroke-linejoin':'round'}));
  for (const cell of state.clues) {
    const [x,y]=cell, done=state.investigated.some(c=>c.join(',')===cell.join(','));
    svg.append(svgElement('path',{d:`M${margin+x*unit+17.5},${margin+y*unit+9}l8,8l-8,8l-8,-8z`,fill:done?'#afa477':'#c49138',stroke:'#fbf7e9','stroke-width':1.5}));
  }
  const target=state.latest?.decision.target;
  if(target && state.outcome==='searching')svg.append(svgElement('rect',{x:margin+target[0]*unit+3,y:margin+target[1]*unit+3,width:29,height:29,rx:5,fill:'none',stroke:'#3d6750','stroke-dasharray':'3 2','stroke-width':1.5}));
  const [x,y]=state.position, robot=svgElement('g',{class:'robot',transform:`translate(${margin+x*unit+17.5} ${margin+y*unit+17.5})`});
  robot.append(svgElement('rect',{x:-11,y:-10,width:22,height:21,rx:6,fill:'#355e4b',stroke:'#fff9df','stroke-width':2}));
  robot.append(svgElement('rect',{x:-8,y:-6,width:16,height:7,rx:3,fill:'#eee9c8'}));
  for(const cx of [-4,4])robot.append(svgElement('circle',{cx,cy:-2.5,r:1.8,fill:'#355e4b'}));
  robot.append(svgElement('path',{d:'M-4,6h8',stroke:'#aabe93','stroke-width':2}));svg.append(robot);
  $('peak').textContent=pct(peak);$('coords').textContent=`X ${String(x).padStart(2,'0')} · Y ${String(y).padStart(2,'0')}`;
}
function render() {
  map(); controls();
  $('mission-title').textContent=state.name;
  $('status').textContent=state.outcome==='searching'?(running?'SEARCHING':state.actions?'PAUSED':'READY'):state.outcome.replaceAll('_',' ').toUpperCase();
  $('status').classList.toggle('found',state.outcome==='found');
  $('battery').textContent=`${state.battery} / ${state.capacity}`;
  $('battery-bar').style.width=pct(state.battery/state.capacity);
  $('time').textContent=state.time_remaining;$('actions').textContent=state.actions;
  $('confidence').textContent=pct(state.summary.confidence);
  $('estimate').textContent=`${coord(state.summary.location)} · ${state.outcome==='found'?'confirmed':'unconfirmed'}`;
  $('status-beliefs').textContent=Object.entries(state.summary.status).map(([name,p])=>`${name} ${pct(p)}`).join('  /  ');
  const latest=state.latest;
  if(latest) {
    const {decision:d,observation:o,belief_after:b}=latest;
    $('action').textContent=`${d.action.kind[0].toUpperCase()+d.action.kind.slice(1)}${d.target?' → '+coord(d.target):''}`;
    $('reason').textContent=d.objective;
    $('facts').textContent=`Return reserve ${d.return_energy} · ${d.travel_steps!==undefined?'Travel '+d.travel_steps+' · Score '+d.score.toFixed(3):'Battery before '+d.battery}`;
    const signal=o.signal||o.evidence?.signal;
    $('observation').textContent=o.contact?`Direct contact at ${coord(o.contact.location)}. EVE is ${o.contact.status}.`:signal?`Measured range ${signal.range} from ${coord(signal.origin)}. Modelled outlier rate ${pct(signal.outlier_rate)}.${o.evidence?' Clue status hint: '+o.evidence.status_hint+'.':''}`:d.action.kind==='recharge'?'Battery restored at a discovered charging station.':`Position ${coord(o.position)}. ${o.terrain.length} local tiles observed; ${o.clues.length} nearby clues visible.`;
    const before=d.belief;
    $('revision').textContent=`Best estimate ${coord(before.location)} (${pct(before.confidence)}) → ${coord(b.location)} (${pct(b.confidence)}).${d.target_changed?' Search target changed from '+coord(d.previous_target)+' to '+coord(d.target)+'.':''}`;
  } else {
    $('action').textContent='Awaiting first decision';$('reason').textContent='Start the mission or advance a single step to watch the agent choose.';$('facts').textContent='';
    $('observation').textContent='The first few tiles are visible. Everything else must be discovered.';
    $('revision').textContent=`Initial best estimate: ${coord(state.summary.location)} at ${pct(state.summary.confidence)}.`;
  }
  $('journal').replaceChildren();
  for(const entry of entries.slice(0,80)) {
    const row=document.createElement('div');row.className='entry';
    const num=document.createElement('span');num.className='stepnum';num.textContent=String(entry.step).padStart(2,'0');
    const content=document.createElement('div'),title=document.createElement('strong'),detail=document.createElement('small'),tag=document.createElement('span');
    title.textContent=`${entry.decision.action.kind.toUpperCase()} ${entry.decision.target?coord(entry.decision.target):''}`;
    detail.textContent=entry.decision.objective;tag.className='tag';tag.textContent=entry.decision.target_changed?'REPLAN':'';
    content.append(title,detail);row.append(num,content,tag);$('journal').append(row);
  }
  if(!entries.length){const p=document.createElement('p');p.className='empty';p.textContent='Your mission log will appear here. No scripted outcomes.';$('journal').append(p);}
  const report=state.report;
  $('report-title').textContent=report?(report.confirmed?'Contact confirmed.':'Search concluded. The evidence remains.'):'The search is still open.';
  $('report-text').textContent=report?report.recommended_next_step:"Finding a likely cell isn't the same as finding EVE. Contact must be confirmed in the environment.";
  $('report-details').textContent=report?`${report.actions} actions · ${report.energy_consumed} energy used · ${report.clues_investigated} clues · ${report.scans} scans`:'';
}
$('play').onclick=()=>{running=!running;clearTimeout(timer);render();if(running)step();};
$('step').onclick=step;$('reset').onclick=reset;$('mission').onchange=reset;
$('heatmap').onchange=()=>state&&map();
$('download').onclick=async()=>{try{const data=await api('/api/export/'+state.session);const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='echo-mission.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){fail(error);}};
(async()=>{try{const missions=await api('/api/missions');$('mission').replaceChildren(...missions.map(m=>{const option=document.createElement('option');option.value=m.id;option.textContent=m.name;return option;}));$('mission').value='first-contact';$('mission').disabled=false;await reset();}catch(error){fail(error);}})();
