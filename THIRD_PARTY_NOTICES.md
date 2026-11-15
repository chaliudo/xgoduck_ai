# Third-party notices

XGO Duck AI is a modified copy of an upstream App and bundles third-party
components. This file lists each component, its pinned revision, its license
and where it lives in this tree.

Entries marked **verify** ship without a license text in this source tree.
Confirm the terms with the rights holder before redistributing this repository
publicly.

## This repository

| Component | Origin | License |
| --- | --- | --- |
| XGO Duck AI App | https://github.com/LuwuDynamics/xgoduck_runtime_arduino, branch `ai-chat-audio-video-tof`, motion baseline `4ce3315c` | Apache-2.0 |
| Modifications in this repository | chaliudo, 2026 | Apache-2.0 |

## Bundled components

| Component | Upstream | Pinned revision | License | Path in this repo |
| --- | --- | --- | --- | --- |
| Microduck RL deployment adapters and policies | https://github.com/pollen-robotics/microduck | `d7560ef0` | Apache-2.0 | `python/proc.py`, `python/rl_core.py`, `python/policy.py` |
| Microduck vocal synthesizer | https://github.com/pollen-robotics/microduck | `d7560ef0` | Apache-2.0 | `python/vendor/microduck_voice/` |
| Luwu OS | https://github.com/LuwuDynamics/luwu_os | `6a444404` | Apache-2.0 | `python/vendor/luwu_os/` |
| Arduino RouterBridge / Arduino_RPClite patches | Arduino s.r.l. | pinned by the App toolchain | MPL-2.0 | `tools/bridge_patch.py` |
| SparkFun VL53L5CX Arduino library | https://github.com/sparkfun/SparkFun_VL53L5CX_Arduino_Library | `24860706` (v1.0.3) | MIT for code, CC BY-SA 4.0 for hardware docs | `sketch/src/vl53l5cx/` |
| WebRTC audio processing module | WebRTC project | binary, no revision recorded | BSD-3-Clause — **verify** | `python/vendor/luwu_os/libs/webrtc_apm/libwebrtc_apm.so` |
| Wake-word models `hey_ducky.onnx`, `xiaoya.onnx` | built from an internal `esp-voice-1` tree, see `provenance/hey-ducky-wakeword.json` | n/a | **unclear — verify before publishing** | `python/models/` |
| RL policy models `xgoduck_*.onnx` | XGO Duck upstream, see `provenance/motion.json` | `4ce3315c` baseline | follow the upstream App license | `python/` |

## License texts

- Apache License 2.0: `LICENSE` and `LICENSES/Apache-2.0.txt`
- Mozilla Public License 2.0: `LICENSES/MPL-2.0.txt`
- Microduck Apache text: `python/vendor/microduck_voice/LICENSE`, attribution in `python/vendor/microduck_voice/NOTICE.md`
- Luwu OS Apache text: `python/vendor/luwu_os/LICENSE`
- SparkFun terms: `sketch/src/vl53l5cx/LICENSE.md`

## Changes in this repository

Modified files must keep a notice that they were changed, per Apache-2.0
section 4(b). This repository changed:

- `python/gamepad.py` — optional enable of gamepad control once per App start.
- `tools/gamepad/input_reader.py` — Bluetooth standard-gamepad stick layout
  (`ABS_Z`/`ABS_RZ`) alongside XInput, and a `device_entries()` helper that
  replaced two-value unpacking of three-value device entries.
- `tools/gamepad/duck-gamepad.service` — comment marking it master-branch only.
- `tools/test-gamepad.py` — regression tests for both of the above.
- `tools/monitor-motion.py` — new motion stability sampler.
- `docs/gamepad.md`, `docs/technical_reference.md` — corrected service name,
  startup enable and monitoring instructions.
- `.gitignore`, `.gitattributes` — repository hygiene for a Linux target.
- `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, `LICENSES/` — added.

## Before publishing

1. Confirm the wake-word model terms with LuwuDynamics; the provenance files
   record only internal source paths.
2. Attach the WebRTC BSD-3-Clause text if the binary is redistributed.
3. Keep `python/vendor/**/NOTICE.md` and `LICENSE` files intact; they satisfy
   the upstream attribution requirements.
