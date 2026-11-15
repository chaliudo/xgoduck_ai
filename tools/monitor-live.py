"""Live Duck health monitor: summaries every few seconds plus threshold alerts.

Samples the local status API at 20 Hz, keeps a rolling window, and prints a
compact line describing what the robot was told to do and how the servos and
IMU responded. Alerts fire on the transition into a bad state so a long,
free-form test session stays readable.

    python3 tools/monitor-live.py --minutes 20 --out data/live-YYYYmmdd.jsonl
"""
import argparse
import json
import math
import time
import urllib.request
from collections import deque

SUMMARY_S = 5.0
ERROR_P95_ALERT = 30.0     # deg between commanded and measured joints
VOLTAGE_ALERT = 6.9        # V, a 2S pack sags here under real load
MISSED_RATE_ALERT = 2.0    # lost 50 Hz periods per second
INFERENCE_ALERT = 45.0     # Hz
GYRO_ALERT = 45.0          # rad/s, body rate above a normal gait


def percentile(values, q):
    if not values:
        return float('nan')
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1)))]


def tilt_deg(gravity):
    if not isinstance(gravity, list) or len(gravity) != 3 or abs(gravity[2]) < 1e-6:
        return float('nan')
    return math.degrees(math.atan2(gravity[1], -gravity[2]))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', default='http://127.0.0.1:9527/api/status')
    parser.add_argument('--rate', type=float, default=20.0)
    parser.add_argument('--minutes', type=float, default=20.0)
    parser.add_argument('--out', default='')
    args = parser.parse_args()

    handle = open(args.out, 'a', encoding='utf-8') if args.out else None
    period = 1.0 / args.rate
    window = deque(maxlen=max(20, int(SUMMARY_S * args.rate)))
    started = time.monotonic()
    deadline = started + args.minutes * 60
    last_summary = 0.0
    last_missed = None
    last_missed_at = None
    active = set()

    def alert(name, text):
        if name in active:
            return
        active.add(name)
        print('[%s] ALERT %s' % (time.strftime('%H:%M:%S'), text), flush=True)

    def clear(name):
        active.discard(name)

    while time.monotonic() < deadline:
        tick = time.monotonic()
        try:
            with urllib.request.urlopen(args.url, timeout=2) as response:
                status = json.load(response)
        except Exception as exc:
            print('[%s] read failed: %s' % (time.strftime('%H:%M:%S'), exc), flush=True)
            time.sleep(period)
            continue

        command = status.get('command') or status.get('twist') or [0.0, 0.0, 0.0]
        try:
            cmd = tuple(round(float(v), 2) for v in command)
        except (TypeError, ValueError):
            cmd = (0.0, 0.0, 0.0)
        gyro = status.get('gyro') or [0.0, 0.0, 0.0]
        try:
            gyro_norm = math.sqrt(sum(float(v) ** 2 for v in gyro))
        except (TypeError, ValueError):
            gyro_norm = 0.0
        targets = status.get('targets') or []
        angles = status.get('angles') or []
        error = float('nan')
        worst_joint = -1
        if isinstance(targets, list) and isinstance(angles, list) and len(targets) == len(angles) and targets:
            gaps = [abs(float(a) - float(t)) for a, t in zip(angles, targets)]
            error = max(gaps)
            worst_joint = gaps.index(error)
        voltage = status.get('voltage_v')
        missed = status.get('loop_missed')
        now = time.monotonic()
        missed_rate = float('nan')
        # Rate over a >=1 s window: the counter is cumulative, so a per-sample
        # delta would always be zero.
        if isinstance(missed, (int, float)):
            if last_missed is None:
                last_missed, last_missed_at = float(missed), now
            elif now - last_missed_at >= 1.0:
                missed_rate = (float(missed) - last_missed) / (now - last_missed_at)
                last_missed, last_missed_at = float(missed), now

        record = dict(t=round(now - started, 2), mode=status.get('mode'),
                      roller=(status.get('roller') or {}).get('enabled'),
                      cmd=cmd, gyro=gyro_norm, tilt=tilt_deg(status.get('gravity')),
                      error=error, joint=worst_joint, volts=voltage,
                      missed_rate=missed_rate, inference=status.get('inference_hz'),
                      fault=bool(status.get('fault_hold')),
                      recovery=(status.get('recovery') or {}).get('phase'))
        window.append(record)
        if handle:
            handle.write(json.dumps(record) + '\n')
            handle.flush()

        # Alerts: fire on entering a bad state, clear when it recovers.
        if record['fault']:
            alert('fault', 'fault_hold: STM32 feedback stalled while commanded %s' % (cmd,))
        else:
            clear('fault')
        if record['recovery'] and record['recovery'] not in ('walk', 'default_pose'):
            alert('fall', 'recovery phase=%s while commanded %s' % (record['recovery'], cmd))
        else:
            clear('fall')
        if error == error and error > ERROR_P95_ALERT:
            alert('error', 'joint %d tracking error %.1f deg, commanded %s'
                  % (worst_joint, error, cmd))
        elif error == error and error < ERROR_P95_ALERT * 0.6:
            clear('error')
        if isinstance(voltage, (int, float)) and voltage < VOLTAGE_ALERT:
            alert('volts', 'bus %.2f V under load, commanded %s' % (voltage, cmd))
        elif isinstance(voltage, (int, float)) and voltage > VOLTAGE_ALERT + 0.2:
            clear('volts')
        if missed_rate == missed_rate and missed_rate > MISSED_RATE_ALERT:
            alert('missed', '%.1f lost 50 Hz periods/s, commanded %s' % (missed_rate, cmd))
        elif missed_rate == missed_rate and missed_rate < 1.0:
            clear('missed')

        if now - last_summary >= SUMMARY_S and window:
            last_summary = now
            gyros = [r['gyro'] for r in window]
            errors = [r['error'] for r in window if r['error'] == r['error']]
            tilts = [r['tilt'] for r in window if r['tilt'] == r['tilt']]
            volts = [float(r['volts']) for r in window if isinstance(r['volts'], (int, float))]
            mean_tilt = sum(tilts) / len(tilts) if tilts else float('nan')
            spread = (math.sqrt(sum((t - mean_tilt) ** 2 for t in tilts) / len(tilts))
                      if len(tilts) > 1 else float('nan'))
            rates = [r['missed_rate'] for r in window if r['missed_rate'] == r['missed_rate']]
            print('[%s] %-6s roller=%-5s cmd=%-18s gyro=%5.1f tilt=%5.1f±%4.1f '
                  'err95=%5.1f joint=%2d vmin=%.2f miss/s=%4.1f inf=%4.1f'
                  % (time.strftime('%H:%M:%S'), record['mode'], record['roller'], str(cmd),
                     sum(gyros) / len(gyros), mean_tilt, spread,
                     percentile(errors, .95), worst_joint,
                     min(volts) if volts else float('nan'),
                     sum(rates) / len(rates) if rates else float('nan'),
                     record['inference'] or 0.0), flush=True)
        time.sleep(max(0.0, period - (time.monotonic() - tick)))

    if handle:
        handle.close()


if __name__ == '__main__':
    main()
