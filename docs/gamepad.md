# Bluetooth gamepad control

Open `http://<duck-host>:9527/gamepad.html`. All navigation and setup text is English.

1. Put an Xbox Bluetooth controller or Switch Pro controller into pairing mode.
2. Select **Scan for controllers**. The scan stops after 30 seconds.
3. Select **Pair & connect** beside the intended controller. Existing pairings offer **Connect**, **Disconnect**, and **Forget**.
4. Wait for **Input ready**. Center both sticks, release all buttons, and select **Enable gamepad control**.

Pairing and enabling the input source do not arm motors. Default buttons are Menu/Start for walk, the bottom face button (Xbox A) for default pose, and the right face button (Xbox B) for torque off. Skating mode is unassigned by default; bind it to switch between the walk and roller models from the controller. Move sticks directly; no LB modifier is required. Centering the sticks zeros movement. In ordinary walking, left Y maps to forward 0.2 / backward 0.18 m/s, left X to strafe ±0.3 m/s, and right X to yaw ±1.0 rad/s. In Roller mode the ranges are forward/backward ±0.4 m/s, strafe 0 and yaw ±0.25 rad/s. The input deadzone is 14% and remaining travel is rescaled to full range.

A Skating mode bound button flips the same state as the **Skating mode** switch on the Control page, not a separate copy. Press it and that page's switch follows on its next status poll; change the switch there and the gamepad reports the new mode. The gamepad page shows the current mode and greys out strafe while Skating is on. Kicking is unavailable while Skating is on: the roller model has no kicking gait, so the Control page and cockpit disable both kick buttons, and voice or MCP kicks are refused with the same reason. The toggle goes through the Control page's own path, so queued voice and phone actions are retired and the cockpit lease is released exactly as a web toggle does. Switching is refused while an action is preparing, while a kick or roulade runs, or before Duck has stood up from a sit; the gamepad page shows that reason.

While gamepad control is enabled, periodic browser movement messages are ignored. Explicit browser mode controls and Torque off remain available. A disconnected/replaced gamepad, stale input snapshot, or failed worker connection disarms and releases the input source. Reconnection requires explicitly enabling control again. Calibration and servo setup release gamepad ownership.

## Enable on startup

Control starts disabled after every App start, by design. To arm the input source automatically, write a settings file into the App directory and restart the App:

```sh
echo '{"auto_enable": true}' > ~/ArduinoApps/xgoduck_ai/data/gamepad-settings.json
docker restart "$(docker ps --filter name=xgoduck_ai --format '{{.Names}}' | head -1)"
```

The App reads the file once at start and then enables control as soon as a supported controller is connected and centred, retrying twice a second, so a controller that connects after start still arms. This only selects the input source: it never presses Walk and never arms motors, and the neutral-stick check still applies. Once control has been enabled, an explicit disable, a disconnect, or entering calibration or servo setup keeps it off for the rest of the session, so the usual "reconnect and enable again" rule still holds. Delete the file, or set `auto_enable` to `false`, to return to manual enable.

## Button binding

Disable gamepad control, choose **Bind** beside Walk / get up, Default pose, Torque off, Pick, Roulade, or Skating mode, then press a single controller button within 15 seconds. Release any held buttons first. Learning consumes input without executing robot actions. A disconnect, timeout, multiple presses, or duplicate assignment leaves existing bindings unchanged. Pick and Roulade are initially unassigned and require walking upright when used. Use **Clear**, **Cancel binding**, or **Restore defaults** as needed; Torque off cannot be cleared. Names use Xbox labels / physical positions, including shoulder buttons, View/Menu, Home, and stick clicks.

Mappings are saved atomically in `data/gamepad-bindings.json` and survive app/board restarts. A file written before Skating mode existed still loads: actions added later start unassigned instead of resetting every binding. Learning runs on the board; press counters from evdev retain short presses between web polls. Disconnect/stale input protection is unchanged.

## Architecture and installation

- `tools/gamepad/server.py`: system service using BlueZ D-Bus for scanning/pairing, with a pairing agent authorized only for the controller explicitly selected in the page. It is not the system default agent.
- `tools/gamepad/input_reader.py`: standard Linux evdev input, requiring both sticks and face buttons. Keyboard and audio-device input nodes are excluded. Both two-stick layouts are accepted: XInput-style pads report the right stick as `ABS_RX/RY`, while Bluetooth standard-gamepad devices such as Xbox over Bluetooth and GameSir pads report it as `ABS_Z/RZ`. Device state is sampled using ioctls so dropped input events are resynchronized.
- `python/gamepad.py`: firmware API and 20 Hz input worker. This does not change the 100 Hz servo loop, 50 Hz policy loop, or 2 Mbps Bridge link.
- The privileged worker exposes only `data/gamepad.sock` (root:arduino, 0660), not a network port. Browser mutations require same-origin requests with `X-Duck-Gamepad: 1`.

On this branch the worker runs as `xgoduck-ai-hardware.service`. `tools/install-ai-support.sh` copies `tools/gamepad/{server,input_reader,unitree_remote,usb_role}.py` into `/usr/local/lib/xgoduck-ai-support/` and generates the unit, which also handles USB role detection and BluFi provisioning. To deploy an edit to one of those files, copy it into that directory and restart the service; do not start a second worker for the same socket:

```sh
sudo install -m 0644 tools/gamepad/input_reader.py /usr/local/lib/xgoduck-ai-support/
sudo systemctl restart xgoduck-ai-hardware.service
```

Do not install `tools/gamepad/duck-gamepad.service` on this branch. That standalone unit belongs to the master branch, hardcodes the `xgoduck_runtime_arduino` App directory, and fails with `226/NAMESPACE` when the App is imported as `xgoduck_ai`. The installer disables it; `xgoduck-ai-hardware.service` already provides the same worker.

The App side reads `data/gamepad.sock` from the App directory, shared with the container. Override `DUCK_GAMEPAD_SOCKET` in other firmware layouts. Restart the Linux app after installing the firmware API; do so with the robot supported and torque disabled.

## Unitree BLE remote

Remotes named `Unitree-*` offer **Connect BLE**. `Unitree-35630A` was verified with FFE0, notification characteristic FFE1 and write characteristic FFE2. The service forces LE/public address through the installed `/usr/bin/gatttool`, discovers handles and the CCCD, subscribes, and writes the eight ASCII bytes `59532b32`. No PIN or OS pairing is needed for this verified device. The BLE protocol reference is https://github.com/legion1581/unitree_ui/blob/main/docs/remote-control.md .

`unitree_remote.py` decodes finite, bounded 20-byte samples into the same input schema as evdev. It preserves button press counters for binding, supports shoulders, triggers, function keys and D-pad, and reports battery level. The app's existing explicit enable, neutral check, identity check and stale-input/disconnect protection apply. Connection selects the remote input but never arms motors. There is no automatic reconnection or silent fallback to another controller after link loss. Select **Connect BLE**, then explicitly enable control again. On other R3 firmware versions, protocol compatibility still needs checking.

## Compatibility

Xbox support requires a Bluetooth-capable controller; older proprietary Xbox Wireless models require a suitable receiver and driver. Input mappings follow Linux gamepad button positions, not Nintendo's printed A/B labels. Switch Pro requires `hid-nintendo`; the stock kernel on this board initially had `CONFIG_HID_NINTENDO` disabled. The Linux v7.0 driver has now been compiled against `7.0.0-g122c2c22d838` and loaded successfully. To reproduce the installation on a matching Linux 7.0 system, run `sudo sh tools/gamepad/install-nintendo-driver.sh`; the installer verifies pinned upstream source checksums. Separate Joy-Cons are not combined into a two-stick controller by this service. Third-party controllers work if Linux exposes the standard two-stick gamepad input capabilities.

Driver source: Linux v7.0 `drivers/hid/hid-nintendo.c` and `hid-ids.h` from https://github.com/torvalds/linux/tree/v7.0/drivers/hid . Compile against the exact running kernel headers; a kernel upgrade requires rebuilding the module. Do not force-load a mismatched module.

## Tests

```sh
python3 tools/test-gamepad.py
python3 tools/test-web-control.py
node tools/test-web-events.js
```

Unit tests cover normalization, deadzone, device filtering, deliberate enable, button edge detection, stop priority, connection loss, input-source handoff, and retained sensor protection. Real Bluetooth pairing and physical button mapping still require a controller in pairing mode.
