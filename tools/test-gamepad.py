"""Pure input mapping + control handoff/disconnect tests; no motors needed."""
import ast
import json
import tempfile
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'python'), str(ROOT/'tools/gamepad')]
from input_reader import normalize, is_gamepad, right_stick_codes, device_entries
# Avoid FastAPI/httpx dependencies for local tests; exercise actual control code.
source = ast.parse((ROOT/'python/gamepad.py').read_text(encoding='utf-8'))
nodes = [n for n in source.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in ('motion_from_input','GamepadControl')]
nodes += [n for n in source.body if isinstance(n, ast.Assign)]
ns = dict(time=time, threading=threading, json=json, Path=Path)
exec(compile(ast.Module(body=nodes, type_ignores=[]), 'gamepad.py', 'exec'), ns)
GamepadControl, motion = ns['GamepadControl'], ns['motion_from_input']


class GamepadTest(unittest.TestCase):
    def setUp(self):
        self.c = Mock(lock=threading.RLock(), mode='off', input_source='gamepad')
        self.c.battery_phase, self.c.generation = 'normal', 0
        self.c.fault_hold = False
        self.c.roller_mode = False
        self.c._imu_job = {'active': False}
        self.c.sitstand_phase, self.c.kick_until = 'idle', 0.
        self.g = GamepadControl.__new__(GamepadControl)
        self.g.controller = self.c
        self.g.wait_for_neutral = False
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.g.bindings_path = Path(self.temp.name)/'bindings.json'
        self.g.bindings = dict(ns['DEFAULT_BINDINGS'])
        self.g.learning = None
        self.g.binding_message = ''
        self.g.enabled, self.g.identity, self.g.buttons, self.g.error = True, 'pad1', {}, ''
        self.g.auto_enable, self.g.auto_done, self.g.next_probe = False, False, 0.0
        self.data = dict(connected=True, stamp=time.monotonic(), id='pad1',
            axes=dict(lx=0, ly=-1, rx=.5, ry=0), buttons=dict(lb=False))

    def test_web_cannot_overwrite_gamepad_commands(self):
        source = ast.parse((ROOT/'python/controller.py').read_text(encoding='utf-8'))
        cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Controller')
        fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'command')
        import math
        ns = dict(math=math, time=time, EXCLUSIVE_MODES=('calibrate','servo_debug'))
        exec(compile(ast.Module(body=[fn], type_ignores=[]), 'controller.py', 'exec'), ns)
        self.c.pick_active = False
        self.c.twist = [.2,0,0]
        result = ns['command'](self.c, twist=[0,0,0])
        self.assertIn('ignored',result)
        self.assertEqual(self.c.twist,[.2,0,0])
        ns['command'](self.c, twist=[.1,0,0], source='gamepad')
        self.assertEqual(self.c.twist,[.1,0,0])

    def test_deadzone_and_bounded_motion(self):
        self.assertEqual(normalize(0,-32768,32767),0)
        self.assertEqual(normalize(128,0,255),0)
        self.assertEqual(normalize(-999,-100,100),-1)
        self.assertEqual(normalize(999,-100,100),1)
        self.assertEqual(motion(self.data),[.2,0.,-.5])
        self.data['buttons']['lb']=False
        self.assertEqual(motion(self.data),[.2,0.,-.5])
        self.data['axes'] = dict(lx=0,ly=0,rx=0,ry=0)
        self.assertEqual(motion(self.data),[0.,0.,0.])

    def test_walking_and_roller_use_the_matching_master_ranges(self):
        self.data['axes'] = dict(lx=1, ly=1, rx=1, ry=0)
        self.assertEqual(motion(self.data), [-.18, -.3, -1.])
        self.assertEqual(motion(self.data, roller=True), [-.4, 0., -.25])
        self.data['axes']['ly'] = -1
        self.assertEqual(motion(self.data)[0], .2)
        self.assertEqual(motion(self.data, roller=True)[0], .4)

    def test_keyboard_and_partial_devices_rejected(self):
        self.assertFalse(is_gamepad({1:[30,31],3:[0,1]}))
        self.assertTrue(is_gamepad({1:[304,305],3:[0,1,3,4]}))

    def test_bluetooth_standard_gamepad_layout(self):
        # Xbox-over-Bluetooth and GameSir pads expose the right stick as ABS_Z/RZ.
        bt = {1:[304,305,307,308], 3:[0,1,2,5,9,10,16,17]}
        self.assertTrue(is_gamepad(bt))
        self.assertEqual(right_stick_codes(bt), (2,5))
        self.assertEqual(right_stick_codes({3:[0,1,3,4]}), (3,4))
        # Entries carry three fields; listing them must not unpack two.
        class Dev:
            name = 'Xbox Wireless Controller'
        entries = device_entries({'/dev/input/event5': (Dev(), 'id', (2,5))}, '/dev/input/event5')
        self.assertEqual(entries, [{'path': '/dev/input/event5',
                                    'name': 'Xbox Wireless Controller', 'selected': True}])

    def test_arm_requires_new_button_press_without_lb(self):
        self.data['buttons']['start']=True
        self.g.consume(self.data)
        self.c.set_mode.assert_called_once_with('policy')
        self.c.set_mode.reset_mock()
        self.g.consume(self.data)
        self.c.set_mode.assert_not_called()
        self.c.command.assert_called_with(twist=[.2,0.,-.5],source='gamepad')

    def test_stop_wins_over_start(self):
        self.data['buttons'].update(east=True,start=True)
        self.g.consume(self.data)
        self.c.set_mode.assert_called_once_with('off')

    def test_disconnect_and_stale_snapshot_follow_retained_gamepad_off_behavior(self):
        for patch in ({'connected':False},{'stamp':time.monotonic()-1},{'id':'replacement'}):
            with self.subTest(patch=patch):
                self.g.enabled=True;self.c.set_mode.reset_mock();self.c.pause_motion.reset_mock()
                self.c.input_source = 'gamepad'
                self.g.consume(dict(self.data,**patch))
                self.assertFalse(self.g.enabled)
                self.c.set_mode.assert_called_once_with('off')
                self.c.pause_motion.assert_not_called()
                self.assertEqual(self.c.input_source,'web')

    def test_calibration_releases_source_without_changing_its_mode(self):
        self.c.mode='calibrate'
        self.g.consume(self.data)
        self.assertFalse(self.g.enabled)
        self.c.set_mode.assert_not_called()

    def test_enabling_requires_neutral_and_does_not_arm(self):
        self.g.client=Mock()
        self.g.client.get.return_value.json.return_value={'input':self.data}
        with self.assertRaisesRegex(ValueError,'Center'):
            self.g.enable(True)
        self.data['axes']={k:0 for k in self.data['axes']};self.data['buttons']={}
        self.c.mode, self.c.input_source = 'policy', 'voice'
        self.g.enable(True)
        self.assertTrue(self.g.enabled)
        self.assertEqual(self.c.input_source, 'voice')
        self.c.set_mode.assert_not_called()
        self.c.pause_motion.assert_not_called()

    def test_auto_enable_latches_once_and_manual_disable_wins(self):
        self.g.client = Mock()
        neutral = dict(connected=True, stamp=time.monotonic(), id='pad1',
                       axes=dict(lx=0, ly=0, rx=0, ry=0), buttons={})
        self.g.client.get.return_value.json.return_value = {'input': neutral}
        self.g.enabled, self.g.auto_enable, self.g.auto_done = False, False, False
        self.assertFalse(self.g.try_auto_enable())
        self.g.auto_enable = True
        self.assertTrue(self.g.try_auto_enable())
        self.assertTrue(self.g.enabled)
        self.g.enable(False)
        self.assertFalse(self.g.enabled)
        self.assertFalse(self.g.try_auto_enable())
        self.assertFalse(self.g.enabled)

    def test_held_axes_wait_for_neutral_after_stop(self):
        self.g.wait_for_neutral = True
        self.g.consume(self.data)
        self.c.command.assert_not_called()
        self.g.consume(dict(self.data, axes={key: 0 for key in self.data['axes']}))
        self.assertFalse(self.g.wait_for_neutral)
        self.g.consume(self.data)
        self.c.command.assert_called_with(twist=[.2, 0., -.5], source='gamepad')

    def learn(self, action='pick'):
        self.g.enabled = False
        self.g.client = Mock()
        self.g.client.get.return_value.json.return_value = {'input': self.data}
        self.g.configure(dict(operation='learn', action=action))

    def test_learning_short_press_persists_without_motion(self):
        self.learn()
        self.data['button_presses'] = {'west': 1}
        self.g.consume(self.data)
        self.assertIsNone(self.g.learning)
        self.assertEqual(self.g.bindings['pick'], 'west')
        self.assertEqual(json.loads(self.g.bindings_path.read_text())['pick'], 'west')
        self.c.set_mode.assert_not_called()
        self.c.command.assert_not_called()
        with unittest.mock.patch.object(threading.Thread, 'start'):
            loaded = GamepadControl(self.c, Mock(), self.g.bindings_path)
        self.assertEqual(loaded.bindings['pick'], 'west')

    def test_binding_file_without_skating_mode_still_loads(self):
        legacy = {key: value for key, value in ns['DEFAULT_BINDINGS'].items() if key != 'roller'}
        legacy['pick'] = 'west'
        self.g.bindings_path.write_text(json.dumps(legacy))
        with unittest.mock.patch.object(threading.Thread, 'start'):
            loaded = GamepadControl(self.c, Mock(), self.g.bindings_path)
        self.assertEqual(loaded.bindings['pick'], 'west')
        self.assertIsNone(loaded.bindings['roller'])
        self.assertEqual(loaded.binding_message, '')

    def test_skating_binding_toggles_the_page_state(self):
        self.g.bindings['roller'] = 'north'
        self.g.access = Mock()
        self.c.roller_mode = False
        self.data['buttons'] = {'north': True}
        self.g.consume(self.data)
        self.g.access.web_roller.assert_called_once_with(True)
        self.g.access.web_roller.reset_mock()
        self.c.roller_mode = True
        self.data['buttons'] = {'north': False}
        self.g.consume(self.data)
        self.data['buttons'] = {'north': True}
        self.g.consume(self.data)
        self.g.access.web_roller.assert_called_once_with(False)

    def test_skating_binding_falls_back_to_the_controller(self):
        self.g.bindings['roller'] = 'north'
        self.g.access = None
        self.c.roller_mode = False
        self.data['buttons'] = {'north': True}
        self.g.consume(self.data)
        self.c.set_roller_mode.assert_called_once_with(True)

    def test_skating_guard_error_surfaces_without_dropping_control(self):
        self.g.bindings['roller'] = 'north'
        self.g.access = Mock()
        self.g.access.web_roller.side_effect = ValueError('wait for kick to finish before switching roller mode')
        self.data['buttons'] = {'north': True}
        self.g.consume(self.data)
        self.assertIn('wait for kick', self.g.error)
        self.assertTrue(self.g.enabled)

    def test_status_reports_skating_mode(self):
        self.c.input_source, self.c.roller_mode = 'gamepad', True
        self.assertTrue(self.g.status()['roller'])
        self.c.roller_mode = False
        self.assertFalse(self.g.status()['roller'])

    def test_learning_waits_for_release_and_rejects_duplicate(self):
        self.data['buttons']['east'] = True
        self.learn()
        self.g.consume(self.data)
        self.assertIsNotNone(self.g.learning)
        self.data['buttons']['east'] = False
        self.g.consume(self.data)
        self.data['buttons']['east'] = True
        self.g.consume(self.data)
        self.assertIsNone(self.g.learning)
        self.assertIsNone(self.g.bindings['pick'])
        self.assertIn('already assigned', self.g.binding_message)

    def test_binding_timeout_disconnect_cancel_and_multiple(self):
        for patch in ({'connected':False}, {'id':'other'}, {'buttons':{'west':True,'north':True}}):
            self.learn()
            self.g.consume(dict(self.data, **patch))
            self.assertIsNone(self.g.learning)
            self.assertIsNone(self.g.bindings['pick'])
        self.learn()
        self.g.learning['until'] = time.monotonic()-1
        self.g.consume(self.data)
        self.assertIsNone(self.g.learning)
        self.learn()
        self.g.configure(dict(operation='cancel'))
        self.assertIsNone(self.g.learning)

    def test_binding_requires_disabled_and_keeps_stop(self):
        with self.assertRaisesRegex(ValueError, 'Disable'):
            self.g.configure(dict(operation='learn',action='pick'))
        self.g.enabled = False
        with self.assertRaisesRegex(ValueError, 'Torque off'):
            self.g.configure(dict(operation='clear',action='off'))
        self.learn()
        self.data['axes'] = dict(lx=0,ly=0,rx=0,ry=0)
        with self.assertRaisesRegex(ValueError, 'cancel'):
            self.g.enable(True)

    def test_custom_actions_and_stop_priority(self):
        self.g.bindings.update(pick='west',roulade='north',off='rb')
        self.data['buttons'] = {'west':True}
        self.g.consume(self.data)
        self.c.start_pick.assert_called_once()
        self.g.consume(self.data)
        self.c.start_pick.assert_called_once()
        self.data['buttons'] = {'north':True}
        self.g.consume(self.data)
        self.c.start_roulade.assert_called_once()
        self.data['buttons'] = {'rb':True,'start':True}
        self.g.consume(self.data)
        self.c.set_mode.assert_called_once_with('off')


if __name__=='__main__': unittest.main()
