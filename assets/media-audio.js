(() => {
  const $ = id => document.getElementById(id);
  let state = null, busy = false, dirty = false, recordKey = '', ttsKey = '', revision = 0;
  function notice(text = '') { $('notice').textContent = text || ''; $('notice').hidden = !text; }
  async function request(path, data = {}) {
    const res = await fetch('/api/media/' + path, {method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Device-Test': '1'},
      body: JSON.stringify(data), signal: AbortSignal.timeout(15000)});
    const body = await res.json();
    if (!res.ok) throw Error(body.error || body.detail || '请求失败。');
    return body;
  }
  function render(s) {
    state = s;
    const a = s.audio, idle = a.state === 'idle', ready = a.available && !busy;
    $('connection').textContent = '已连接 ' + location.hostname;
    $('audioBadge').textContent = ({playing: '播放中', recording: '录音中', synthesizing: '正在合成语音', cancelling: '正在停止'})[a.state] || (a.available ? '已连接' : '未找到');
    $('recBadge').textContent = a.state === 'recording' ? '录音中' : a.available ? '已连接' : '未找到';
    if (!dirty) {
      if (a.volume != null) $('volume').value = a.volume;
      $('volumeValue').textContent = a.volume == null ? '—' : a.volume + '%';
      $('volumeStatus').textContent = a.volume_error || (a.available ? '已应用到 USB 扬声器' : '未找到 USB 音频设备');
    }
    $('volume').disabled = !ready;
    $('applyVolume').disabled = !ready || !dirty;
    $('play').disabled = !ready || !idle;
    $('audioStop').disabled = busy || idle;
    $('record').disabled = !ready || !idle;
    $('recordStop').disabled = busy || a.state !== 'recording';
    $('seconds').disabled = busy || !idle;
    $('replay').disabled = !ready || !idle || !a.recording;
    $('audioError').textContent = a.error || '';
    $('recProgress').textContent = a.state === 'recording' ? a.elapsed.toFixed(1) + ' 秒' : '';
    $('recording').hidden = !a.recording;
    if (!a.recording) recordKey = '';
    if (a.recording) {
      const r = a.recording, key = JSON.stringify(r);
      $('recordStats').textContent = `${r.duration} 秒 · ${r.rate / 1000} kHz · ${r.dbfs} dBFS · ${r.clipped ? '检测到削波' : r.rms < .0001 ? '信号过弱' : '无削波'}`;
      $('level').style.width = Math.min(100, Math.max(0, (r.dbfs + 60) / 60 * 100)) + '%';
      if (key !== recordKey) { recordKey = key; $('player').src = '/api/media/recording?t=' + Date.now(); }
    }
    const t = s.tts || {};
    $('ttsBadge').textContent = t.configured ? '语音已配置' : '语音未配置';
    $('ttsSpeak').disabled = !ready || !idle || !t.configured || !$('ttsText').value.trim();
    $('ttsReplay').disabled = !ready || !idle || !t.audio;
    $('ttsStop').disabled = busy || idle;
    $('ttsText').disabled = !!t.busy;
    $('ttsError').textContent = t.error || '';
    $('ttsProgress').textContent = t.busy ? `正在合成语音 · ${a.elapsed.toFixed(1)} 秒` : t.audio ? `已生成音频 · ${t.audio.duration} 秒` : '';
    $('ttsResult').hidden = !t.audio;
    if (t.audio && String(t.audio.version) !== ttsKey) { ttsKey = String(t.audio.version); $('ttsPlayer').src = '/api/media/tts/audio?t=' + ttsKey; }
    if (!t.audio) ttsKey = '';
  }
  async function act(path, data = {}, apply = false) {
    if (busy) return;
    busy = true; revision++; if (state) render(state); notice();
    try {
      if (apply && dirty) { state = await request('audio/volume', {volume: +$('volume').value}); dirty = false; }
      render(await request(path, data));
    } catch (e) { notice(e.message); }
    finally { busy = false; if (state) render(state); }
  }
  $('volume').oninput = () => { dirty = true; $('volumeValue').textContent = $('volume').value + '%'; $('volumeStatus').textContent = '未应用'; if (state) render(state); };
  $('applyVolume').onclick = async () => {
    if (busy) return;
    busy = true; revision++; if (state) render(state); notice();
    try { state = await request('audio/volume', {volume: +$('volume').value}); dirty = false; }
    catch (e) { notice(e.message); }
    finally { busy = false; if (state) render(state); }
  };
  $('play').onclick = () => act('audio/play', {source: 'music'}, true);
  $('audioStop').onclick = $('recordStop').onclick = $('ttsStop').onclick = () => act('audio/stop');
  $('record').onclick = () => { $('player').pause(); act('audio/record', {seconds: +$('seconds').value}); };
  $('replay').onclick = () => { $('player').pause(); act('audio/play', {source: 'recording'}, true); };
  $('ttsText').oninput = () => { $('ttsCount').textContent = $('ttsText').value.length + ' / 200'; if (state) render(state); };
  $('ttsSpeak').onclick = () => { $('ttsPlayer').pause(); act('tts/speak', {text: $('ttsText').value, volume: +$('volume').value}, true); };
  $('ttsReplay').onclick = () => { $('ttsPlayer').pause(); act('audio/play', {source: 'tts'}, true); };
  async function poll() {
    const version = revision;
    try {
      if (busy || document.hidden) return;
      const res = await fetch('/api/media/status', {signal: AbortSignal.timeout(7000)});
      if (!res.ok) throw Error();
      const s = await res.json();
      if (!busy && version === revision) render(s);
    } catch (e) {
      if (version !== revision) return;
      $('connection').textContent = '连接已断开，正在重试…';
      document.querySelectorAll('button, input, select').forEach(el => el.disabled = true);
    } finally { setTimeout(poll, 1000); }
  }
  poll();
})();
