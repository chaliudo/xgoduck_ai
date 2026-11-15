(() => {
  const $ = id => document.getElementById(id);
  // Tolerate a cached HTML document that predates an element: the script tag is
  // versioned, the page is not, so a new script can run against old markup.
  const setText = (id, text) => { const el = $(id); if (el) el.textContent = text; };
  let busy = false, state = null, devicesKey = '', inputsKey = '', revision = 0, bindingsKey = '', actionError = '';
  const labels = {south:'A / 下', east:'B / 右', west:'X / 左', north:'Y / 上', lb:'LB / L', rb:'RB / R', back:'View / −', start:'Menu / +', guide:'Home', ls:'左摇杆按下', rs:'右摇杆按下', lt:'LT / L2', rt:'RT / R2', f1:'F1', f3:'F3', up:'十字键上', down:'十字键下', left:'十字键左', right:'十字键右'};
  const actions = {walk:'行走 / 起身', hold:'默认姿态', off:'卸力', pick:'叼取', roulade:'翻滚', roller:'滑行模式'};
  function error(text='') { $('error').textContent = text; $('error').hidden = !text; }
  async function act(action, data={}) {
    if (busy) return;
    busy = true; actionError = ''; revision++; if (state) render(state); error();
    try {
      const r = await fetch('/api/gamepad/' + action, {method:'POST',
        headers:{'Content-Type':'application/json','X-Duck-Gamepad':'1'}, body:JSON.stringify(data),
        signal:AbortSignal.timeout(12000)});
      const body = await r.json(); if (!r.ok) throw Error(body.error || '请求失败。');
      state = body;
    } catch(e) { actionError=e.message; error(actionError); }
    finally { busy = false; devicesKey = ''; if (state) render(state); }
  }
  function render(s) {
    state = s;
    const b=s.bluetooth, input=s.input, c=s.control, working=busy || b.busy;
    $('connection').textContent='已连接 ' + location.hostname;
    $('adapter').textContent=b.available ? b.powered ? '蓝牙已开启' : '蓝牙已关闭' : '不可用';
    $('scan').disabled=working || !b.available || b.discovering;
    $('stopScan').disabled=working || !b.discovering;
    $('scanStatus').textContent=busy ? '正在发送请求…' : b.busy ? '配对 / 连接中…' : b.discovering ? `扫描中 · ${b.scan_remaining || 0} 秒` : '';
    const key=JSON.stringify([(b.devices || []).map(({rssi,...d})=>d).sort((a,b)=>a.address.localeCompare(b.address)),working]);
    if (key !== devicesKey) {
      devicesKey=key; $('devices').replaceChildren();
      for (const d of b.devices || []) {
        const row=document.createElement('div');row.className='device-row';
        const info=document.createElement('div');info.className='device-info';
        const title=document.createElement('strong');title.textContent=d.name;
        const detail=document.createElement('p');detail.className='small';
        detail.textContent=`${d.address} · ${d.connected ? '已连接' : d.paired ? '已配对' : '未配对'}`;
        info.append(title,detail);
        if(d.kind==='unitree_ble'){
          const note=document.createElement('p');note.className='small';
          note.textContent='Unitree BLE 遥控器 · 直连，无需 PIN 码。';
          info.append(note);
        }
        row.append(info);
        const buttons=document.createElement('div');buttons.className='row';
        const button=(label,action)=>{const el=document.createElement('button');el.textContent=label;el.disabled=working;el.onclick=()=>act(action,{address:d.address});buttons.append(el);};
        if(d.connected || d.connect_supported!==false) {
          button(d.connected ? '断开' : d.kind==='unitree_ble' ? '连接 BLE' : d.paired ? '连接' : '配对并连接',d.connected?'disconnect':'connect');
        } else {
          const detected=document.createElement('span');detected.className='badge';detected.textContent='已检测到';buttons.append(detected);
        }
        if(d.paired)button('忘记','forget');
        row.append(buttons);$('devices').append(row);
      }
    }
    $('empty').hidden=!!b.devices?.length;
    $('empty').textContent=b.discovering?'正在搜索处于配对模式的手柄…':'未发现手柄。请让手柄进入配对模式后扫描。';
    const ikey=JSON.stringify(input.devices);
    if (ikey !== inputsKey) {
      inputsKey=ikey;$('inputDevice').replaceChildren();
      // Without a placeholder, a lone HID option looks selected even while
      // the actual input source is a disconnected BLE remote.
      if(input.devices?.length&&!input.devices.some(d=>d.selected)){
        const option=document.createElement('option');option.value='';option.textContent='选择手柄…';option.disabled=true;option.selected=true;$('inputDevice').append(option);
      }
      for(const d of input.devices || []) {const option=document.createElement('option');option.value=d.path;option.textContent=d.name;option.selected=d.selected;$('inputDevice').append(option);}
      if(!input.devices?.length){const option=document.createElement('option');option.textContent='未连接手柄';$('inputDevice').append(option);}
    }
    $('inputDevice').disabled=working || !input.devices?.length || c.enabled;
    $('controlState').textContent=c.enabled?'已启用':'关闭';
    $('enable').disabled=working || c.enabled || !!c.learning || !input.connected;
    $('disable').disabled=busy || !c.enabled;
    $('inputStatus').textContent=input.connected?input.name+' · 输入就绪'+(input.kind==='unitree_ble' ? ` · 电量 ${input.battery}%` : ''):input.devices?.length?'请在下方选择手柄以启用手柄控制。':b.devices?.some(d=>d.connected)?'蓝牙已连接，正在等待受支持的手柄输入设备。':'正在等待手柄输入设备。';
    setText('skatingStatus', c.roller?'滑行模式：开启（滚轮模型，不支持横移）':'滑行模式：关闭（普通行走）');
    setText('strafeCell', c.roller?'滑行模式下忽略':'左右横移');
    const a=input.axes || {lx:0,ly:0,rx:0,ry:0};
    $('leftStick').style.transform=`translate(${a.lx*38}px,${a.ly*38}px)`;
    $('rightStick').style.transform=`translate(${a.rx*38}px,${a.ry*38}px)`;
    $('buttons').textContent='按键：'+(Object.entries(input.buttons||{}).filter(([,down])=>down).map(([name])=>labels[name] || name.toUpperCase()).join(' · ')||'—');
    const bk=JSON.stringify([c.bindings,c.learning,c.enabled,working,input.connected]);
    if(bk!==bindingsKey){
      bindingsKey=bk;$('bindings').replaceChildren();
      for(const [action,title] of Object.entries(actions)){
        const row=document.createElement('div');row.className='binding-row';
        const info=document.createElement('div');
        const name=document.createElement('strong');name.textContent=title;
        const value=document.createElement('span');value.className='binding-value';
        value.textContent=c.learning===action?'请按一个按键…':labels[c.bindings?.[action]] || '未分配';
        info.append(name,value);row.append(info);
        const buttons=document.createElement('div');buttons.className='row';
        const bind=document.createElement('button');bind.textContent=c.learning===action?'监听中…':'绑定';
        bind.disabled=working || c.enabled || !!c.learning || !input.connected || !c.bindings;
        bind.onclick=()=>act('bindings',{operation:'learn',action});buttons.append(bind);
        if(action!=='off'){
          const clear=document.createElement('button');clear.textContent='清除';
          clear.disabled=working || c.enabled || !!c.learning || !c.bindings?.[action];
          clear.onclick=()=>act('bindings',{operation:'clear',action});buttons.append(clear);
        }
        row.append(buttons);$('bindings').append(row);
      }
    }
    $('cancelBinding').hidden=!c.learning;$('cancelBinding').disabled=busy;
    $('resetBindings').disabled=working || c.enabled || !!c.learning || !c.bindings;
    $('bindingStatus').textContent=!c.bindings?'请重启小鸭 App 以启用可配置绑定。':c.enabled?'修改绑定前请先关闭手柄控制。':c.binding_message || '点「绑定」，然后按一个手柄按键。';
    error(actionError || b.error || c.error || '');
  }
  $('scan').onclick=()=>act('scan');$('stopScan').onclick=()=>act('stop-scan');
  $('enable').onclick=()=>act('control',{enabled:true});$('disable').onclick=()=>act('control',{enabled:false});
  $('inputDevice').onchange=()=>act('select',{path:$('inputDevice').value});
  $('cancelBinding').onclick=()=>act('bindings',{operation:'cancel'});
  $('resetBindings').onclick=()=>act('bindings',{operation:'reset'});
  async function poll(){const v=revision;try{if(busy||document.hidden)return;const r=await fetch('/api/gamepad/status',{signal:AbortSignal.timeout(4000)});if(r.status===404)throw Error('请重启小鸭 App 以启用手柄支持。');if(!r.ok)throw Error('连接已断开，正在重试…');const s=await r.json();if(!busy&&v===revision)render(s);}catch(e){$('connection').textContent=e.message||'连接已断开，正在重试…';document.querySelectorAll('button,select').forEach(el=>el.disabled=true);}finally{setTimeout(poll,500);}}
  poll();
})();
