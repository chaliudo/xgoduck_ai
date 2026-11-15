/* Browser-local audio lifecycle only; no board, microphone or cloud requests. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const assets=path.join(__dirname,'../assets'),tick=()=>new Promise(resolve=>setImmediate(resolve));
class Element extends EventTarget {
  constructor(){super();this.attributes={};this.textContent='';}
  setAttribute(name,value){this.attributes[name]=value;}
  click(){this.dispatchEvent(new Event('click'));}
}
function setup(){
  const elements=Object.fromEntries(['bindingDialog','startupPreviewStatus','previewStartupNetwork','previewStartupVoice','language'].map(id=>[id,new Element()]));
  const window=new EventTarget(),document=Object.assign(new EventTarget(),{hidden:false,documentElement:{},getElementById:id=>elements[id],querySelectorAll:()=>[]});
  const audio=[];
  class Audio {
    constructor(){audio.push(this);this.paused=true;}
    async play(){this.paused=false;await this.wait;}
    pause(){this.paused=true;}
    removeAttribute(name){if(name==='src')this.src='';}
    load(){}
  }
  const context=vm.createContext({window,document,Audio,navigator:{language:'zh-CN'},CustomEvent:class extends Event{},fetch:()=>{throw Error('Startup examples must not contact a device or cloud API.');}});
  for(const file of ['mobile-i18n.js','mobile-startup.js'])vm.runInContext(fs.readFileSync(path.join(assets,file),'utf8'),context);
  return {elements,window,document,audio,Audio};
}
(async()=>{
  const s=setup(),e=s.elements;
  assert.equal(s.audio.length,0,'Opening the page must not preload or autoplay sounds.');
  e.previewStartupNetwork.click();await tick();const network=s.audio[0];
  assert.equal(network.src,'/startup-network.wav');assert.equal(e.previewStartupNetwork.textContent,'停止');assert.equal(e.previewStartupNetwork.attributes['aria-pressed'],'true');
  e.previewStartupVoice.click();await tick();const voice=s.audio[1];assert(network.paused);assert.equal(network.src,'');assert.equal(voice.src,'/startup-voice.wav');
  network.onended();assert.equal(e.previewStartupVoice.attributes['aria-pressed'],'true','A late event from a previous example must not stop the current one.');
  assert.equal(e.previewStartupVoice.textContent,'停止');assert.match(e.startupPreviewStatus.textContent,/语音服务就绪/);
  voice.onended();assert.equal(e.previewStartupVoice.textContent,'试听');assert(voice.paused);assert.match(e.startupPreviewStatus.textContent,/试听结束/);
  e.previewStartupNetwork.click();await tick();e.previewStartupNetwork.click();assert(s.audio.at(-1).paused);assert.equal(e.startupPreviewStatus.textContent,'已停止试听');
  e.previewStartupVoice.click();await tick();e.bindingDialog.dispatchEvent(new Event('close'));assert(s.audio.at(-1).paused);assert(e.startupPreviewStatus.hidden);
  e.previewStartupVoice.click();await tick();s.document.hidden=true;s.document.dispatchEvent(new Event('visibilitychange'));assert(s.audio.at(-1).paused);
  s.document.hidden=false;e.previewStartupNetwork.click();await tick();s.window.dispatchEvent(new Event('pagehide'));assert(s.audio.at(-1).paused);
  const play=s.Audio.prototype.play;s.Audio.prototype.play=async()=>{throw Error('Media blocked');};
  e.previewStartupNetwork.click();await tick();assert.match(e.startupPreviewStatus.textContent,/试听失败/);assert.equal(e.previewStartupNetwork.attributes['aria-pressed'],'false');s.Audio.prototype.play=play;
  let release;s.Audio.prototype.play=async function(){this.paused=false;await new Promise(resolve=>release=resolve);};
  e.previewStartupNetwork.click();const delayed=s.audio.at(-1);e.previewStartupNetwork.click();release();await tick();assert(delayed.paused);assert.equal(e.previewStartupNetwork.attributes['aria-pressed'],'false');
  s.Audio.prototype.play=play;e.previewStartupVoice.click();await tick();s.audio.at(-1).onerror();assert.match(e.startupPreviewStatus.textContent,/试听失败/);
  console.log('PASS: no preload/autoplay/API writes; two local sounds; single playback, stop/end, stale events, Chinese-only labels, close/hide/page exit, load and play errors.');
})().catch(error=>{console.error(error);process.exitCode=1;});
