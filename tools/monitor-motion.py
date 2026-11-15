#!/usr/bin/env python3
"""Sample XGO Duck motion from port 9527 and report gait stability.

Runs on the board over the local API; standard library only.

    python3 tools/monitor-motion.py                    # 90 s of walking, 15 min cap
    python3 tools/monitor-motion.py --wall-clock --seconds 60
    python3 tools/monitor-motion.py --analyze data/motion-20261114-201500.jsonl

Capture writes JSON Lines so a run can be re-analyzed later or shared.
The report separates standing from walking and never treats a fixture as a gait.
"""
import argparse
import json
import math
import statistics
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODES_MOVING = ('policy', 'hold')
MOTION_THRESHOLD = 0.05


def sample(url, timeout=2.0):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def row_of(status, started):
    command = status.get('command') or [0.0, 0.0, 0.0]
    mode = status.get('mode')
    return {
        't': round(time.monotonic() - started, 3),
        'mode': mode,
        'cmd': command,
        'moving': mode in MODES_MOVING and max(abs(float(x)) for x in command) > MOTION_THRESHOLD,
        'gyro': status.get('gyro_corrected') or status.get('gyro'),
        'acc': status.get('acc_corrected'),
        'grav': status.get('gravity'),
        'yaw': (status.get('heading_hold') or {}).get('yaw_deg'),
        'hold': (status.get('heading_hold') or {}).get('active'),
        'fhz': status.get('feedback_hz'),
        'fage': status.get('feedback_age_ms'),
        'interval': (status.get('receive_interval_ms') or {}).get('mean'),
        'ihz': status.get('inference_hz'),
        'imiss': status.get('loop_missed'),
        'bad': status.get('bad_frames'),
        'gaps': status.get('sequence_gaps'),
        'overrun': status.get('mcu_overruns'),
        'work_us': status.get('mcu_work_us'),
        'fault': status.get('fault_hold'),
        'rec': (status.get('recovery') or {}).get('phase'),
        'batt': (status.get('battery') or {}).get('voltage_v'),
        'tof': (status.get('obstacle_avoidance') or {}).get('front_distance_mm'),
        'tg': status.get('targets'),
        'ang': status.get('angles'),
        'vel': status.get('velocities'),
    }


def capture(args):
    url = 'http://%s:%d/api/status' % (args.host, args.port)
    out_path = Path(args.out) if args.out else ROOT / ('data/motion-%s.jsonl' % datetime.now().strftime('%Y%m%d-%H%M%S'))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    deadline = started + args.timeout * 60
    period = 1.0 / args.rate
    motion = 0.0
    rows = 0
    errors = 0
    previous = started
    print('sampling %s at %.0f Hz; stop after %.0f s of %s, %.0f min cap' % (
        url, args.rate, args.seconds, 'wall time' if args.wall_clock else 'walking',
        args.timeout), file=sys.stderr)
    with out_path.open('w') as handle:
        while time.monotonic() < deadline:
            tick = time.monotonic()
            try:
                row = row_of(sample(url), started)
                handle.write(json.dumps(row) + '\n')
                rows += 1
                if row['moving']:
                    motion += tick - previous
                previous = tick
            except Exception as exc:
                errors += 1
                handle.write(json.dumps({'t': round(time.monotonic() - started, 3), 'err': str(exc)}) + '\n')
            if args.wall_clock:
                done = tick - started >= args.seconds
            else:
                done = motion >= args.seconds
            if done:
                break
            time.sleep(max(0.0, period - (time.monotonic() - tick)))
    print('captured %d samples, %.1f s of motion, %d errors -> %s' % (rows, motion, errors, out_path), file=sys.stderr)
    return out_path


def load(path):
    rows = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if 'err' in row or not isinstance(row.get('gyro'), list):
            continue
        rows.append(row)
    return rows


def mean(values):
    return sum(values) / len(values) if values else float('nan')


def rms(values):
    return math.sqrt(sum(v * v for v in values) / len(values)) if values else float('nan')


def percentile(values, fraction):
    if not values:
        return float('nan')
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def dominant_hz(series, samples_per_s, low=0.5, high=4.0, step=0.1):
    """Band-limited DFT magnitude peak, enough for a 1-3 Hz gait."""
    if len(series) < 32 or samples_per_s <= 0:
        return float('nan'), 0.0
    centre = mean(series)
    window = [v - centre for v in series]
    best_hz, best_power, total = float('nan'), 0.0, 0.0
    frequency = low
    while frequency <= high:
        omega = 2.0 * math.pi * frequency / samples_per_s
        real = sum(v * math.cos(omega * i) for i, v in enumerate(window))
        imag = sum(v * math.sin(omega * i) for i, v in enumerate(window))
        power = real * real + imag * imag
        total += power
        if power > best_power:
            best_hz, best_power = frequency, power
        frequency += step
    return best_hz, (100.0 * best_power / total if total else 0.0)


def tilt_deg(gravity):
    """Roll and pitch from the gravity vector; z points down in this frame."""
    gx, gy, gz = gravity
    down = -gz if abs(gz) > 1e-6 else 1e-6
    return math.degrees(math.atan2(gy, down)), math.degrees(math.atan2(gx, down))


def tracking(rows):
    """Per-joint |commanded - measured| in degrees while moving."""
    errors = {}
    for row in rows:
        if not row.get('moving'):
            continue
        targets, angles = row.get('tg'), row.get('ang')
        if not isinstance(targets, list) or not isinstance(angles, list) or len(targets) != len(angles):
            continue
        for index, (target, angle) in enumerate(zip(targets, angles)):
            try:
                errors.setdefault(index, []).append(abs(float(angle) - float(target)))
            except (TypeError, ValueError):
                continue
    return errors


def report(rows, stream=sys.stdout):
    if not rows:
        print('No usable samples in the capture.', file=stream)
        return 1
    duration = rows[-1]['t'] - rows[0]['t']
    moving = [row for row in rows if row.get('moving')]
    idle = [row for row in rows if not row.get('moving')]
    span = moving if len(moving) >= 10 else rows
    label = 'walking' if len(moving) >= 10 else 'all samples (not enough walking data)'
    rate = len(rows) / duration if duration > 0 else float('nan')

    print('== XGO Duck motion stability ==', file=stream)
    print('capture   %.1f s, %d samples (%.1f Hz), %.1f s walking, %.1f s standing' % (
        duration, len(rows), rate, len(moving) / max(rate, 1e-9), len(idle) / max(rate, 1e-9)), file=stream)
    modes = sorted({row.get('mode') for row in rows if row.get('mode')})
    print('modes     %s   analysis basis: %s' % (', '.join(modes) or '-', label), file=stream)

    warnings = []

    voltages = [float(row['batt']) for row in rows if isinstance(row.get('batt'), (int, float))]
    if voltages:
        print('battery   start %.2f V, end %.2f V, min %.2f V (2S: full 8.40 V, 3.40 V/cell = 6.80 V)' % (
            voltages[0], voltages[-1], min(voltages)), file=stream)
        if min(voltages) < 6.8:
            warnings.append('battery dipped to %.2f V; a 2S pack below 6.80 V is nearly empty and sags under servo load' % min(voltages))

    missed = [row['imiss'] for row in rows if isinstance(row.get('imiss'), (int, float))]
    if len(missed) >= 2:
        total = missed[-1] - missed[0]
        per_s = total / duration if duration > 0 else float('nan')
        print('control   %d missed 50 Hz periods in %.0f s (%.2f /s, %.2f%% of cycles, effective %.1f Hz)' % (
            total, duration, per_s, 100.0 * per_s / 50.0, 50.0 - per_s), file=stream)
        if per_s > 0.5:
            warnings.append('the 50 Hz control loop misses %.2f periods/s; every miss is a 20 ms gap in servo targets' % per_s)

    inference = [float(row['ihz']) for row in span if isinstance(row.get('ihz'), (int, float))]
    if inference:
        print('inference %.1f Hz mean, %.1f Hz min (target 50.0)' % (mean(inference), min(inference)), file=stream)
        if mean(inference) < 47.0:
            warnings.append('policy inference averages %.1f Hz, so the gait is clocked below its trained rate' % mean(inference))

    feedback = [float(row['fhz']) for row in span if isinstance(row.get('fhz'), (int, float))]
    age = [float(row['fage']) for row in span if isinstance(row.get('fage'), (int, float))]
    if feedback:
        print('feedback  %.1f Hz mean, p95 age %.1f ms, max %.1f ms' % (
            mean(feedback), percentile(age, .95), max(age) if age else float('nan')), file=stream)
    if age and percentile(age, .95) > 30.0:
        warnings.append('STM32 feedback age p95 is %.0f ms; the 100 Hz loop is jittering' % percentile(age, .95))

    faults = [row for row in rows if row.get('fault')]
    if faults:
        warnings.append('feedback hold engaged in %d samples; motion paused mid-gait' % len(faults))

    for axis, name in enumerate('xyz'):
        values = [float(row['gyro'][axis]) for row in span if isinstance(row.get('gyro'), list) and len(row['gyro']) > axis]
        if not values:
            continue
        hz, share = dominant_hz(values, rate) if axis < 2 else (float('nan'), 0.0)
        print('gyro %s    rms %.2f rad/s, peak %.2f, dominant %s' % (
            name, rms(values), max(abs(v) for v in values),
            ('%.2f Hz (%.0f%% of 0.5-4 Hz power)' % (hz, share)) if hz == hz else 'n/a'), file=stream)

    tilts = [tilt_deg(row['grav']) for row in span if isinstance(row.get('grav'), list) and len(row['grav']) == 3]
    if tilts:
        rolls = [t[0] for t in tilts]
        pitches = [t[1] for t in tilts]
        print('attitude  roll %.1f deg mean, %.2f std | pitch %.1f deg mean, %.2f std' % (
            mean(rolls), statistics.pstdev(rolls) if len(rolls) > 1 else 0.0,
            mean(pitches), statistics.pstdev(pitches) if len(pitches) > 1 else 0.0), file=stream)
        wobble = max(statistics.pstdev(rolls) if len(rolls) > 1 else 0.0,
                     statistics.pstdev(pitches) if len(pitches) > 1 else 0.0)
        if wobble > 3.0:
            warnings.append('body tilt varies %.1f deg around its mean while walking; the gait is rocking, not gliding' % wobble)

    straight = [row for row in moving if isinstance(row.get('cmd'), list) and len(row['cmd']) >= 3
                and abs(float(row['cmd'][2])) < 0.05 and float(row['cmd'][0]) > 0.05]
    if len(straight) >= 20:
        yaws = [float(row['yaw']) for row in straight if isinstance(row.get('yaw'), (int, float))]
        if len(yaws) >= 2:
            elapsed = straight[-1]['t'] - straight[0]['t']
            drift = yaws[-1] - yaws[0]
            print('heading   straight-line drift %.1f deg over %.1f s (%.1f deg/s), yaw spread %.1f deg' % (
                drift, elapsed, drift / elapsed if elapsed > 0 else 0.0,
                max(yaws) - min(yaws)), file=stream)
            if abs(drift / elapsed if elapsed > 0 else 0) > 5.0:
                warnings.append('straight walking yaws %.1f deg/s; heading hold is not closing the loop' % (drift / elapsed))

    errors = tracking(rows)
    if errors:
        print('tracking  |commanded - measured| per joint, degrees:', file=stream)
        worst = []
        for index in sorted(errors):
            values = errors[index]
            worst.append((percentile(values, .95), index, mean(values), max(values)))
        for p95, index, avg, peak in sorted(worst, reverse=True)[:6]:
            print('          joint %2d  mean %.2f  p95 %.2f  max %.2f' % (index, avg, p95, peak), file=stream)
        bad = [w for w in worst if w[0] > 3.0]
        if bad:
            warnings.append('%d joints lag more than 3 deg at p95; check KP/KD and servo load' % len(bad))

    velocities = [row.get('vel') for row in moving if isinstance(row.get('vel'), list)]
    if velocities and all(abs(v) < 1e-6 for row in velocities for v in row):
        warnings.append('joint velocities are exactly zero in every walking sample; the policy likely sees no velocity feedback')

    print('', file=stream)
    if warnings:
        print('findings:', file=stream)
        for index, text in enumerate(warnings, 1):
            print('  %d. %s' % (index, text), file=stream)
    else:
        print('findings: no stability warning crossed its threshold.', file=stream)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=9527)
    parser.add_argument('--seconds', type=float, default=90.0,
                        help='capture length in seconds (walking time unless --wall-clock)')
    parser.add_argument('--wall-clock', action='store_true',
                        help='count --seconds as elapsed time instead of walking time')
    parser.add_argument('--timeout', type=float, default=15.0, help='hard capture limit in minutes')
    parser.add_argument('--rate', type=float, default=20.0, help='samples per second')
    parser.add_argument('--out', default=None)
    parser.add_argument('--analyze', default=None, help='report on an existing capture')
    args = parser.parse_args()

    if args.analyze:
        return report(load(args.analyze))
    path = capture(args)
    return report(load(path))


if __name__ == '__main__':
    sys.exit(main())
