(() => {
  const button=document.getElementById('usbHost'), status=document.getElementById('usbStatus');
  if(!button||!status)return;
  let current=null,busy=false;
  function render(usb){
    current=usb;button.disabled=busy||!usb?.available;
    button.setAttribute('aria-checked',String(!!usb?.host));
    button.textContent=busy?'正在切换…':usb?.host?'USB Host：已开启':'USB Host：已关闭';
    status.textContent=usb?.error||(!usb?'USB 控制暂不可用。':usb.host?'Host 模式 · 可连接 USB 外设':'Device 模式 · 可用 USB 连接电脑');
  }
  button.onclick=async()=>{
    if(busy||!current?.available)return;
    const host=!current.host;busy=true;render(current);
    try{
      const response=await fetch('/api/gamepad/usb',{method:'POST',headers:{'Content-Type':'application/json','X-Duck-Gamepad':'1'},body:JSON.stringify({host}),signal:AbortSignal.timeout(12000)});
      const data=await response.json();if(!response.ok)throw Error(data.error||'USB 模式切换失败。');
      current=data.usb;
    }catch(e){status.textContent=e.message;busy=false;button.disabled=!current?.available;button.textContent=current?.host?'USB Host：已开启':'USB Host：已关闭';return;}
    busy=false;render(current);
  };
  async function poll(){try{if(busy||document.hidden)return;const response=await fetch('/api/gamepad/status',{signal:AbortSignal.timeout(4000)});if(!response.ok)throw Error();const data=await response.json();if(!busy)render(data.usb);}catch{if(!busy)render(null);}finally{setTimeout(poll,2000);}}
  poll();
})();
