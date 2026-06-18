"""Tests for the Camera Control shortcut builder (stdlib unittest only).

Run from the repo root:
    python3 -m unittest discover -s tests

The tests import src/build.py and inspect the generated shortcut structure
(`build.out`) directly — no file output or external tools required.
"""
import os
import re
import sys
import unittest
import plistlib
from collections import Counter, defaultdict

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
sys.path.insert(0, SRC)
import build  # noqa: E402

OUT = build.out
ACTS = OUT['WFWorkflowActions']

# A real `get_network_conf` response (from the RL500), used to test the
# rtmp1_mrl extraction regex against actual device output.
SAMPLE_CONF = '''dhcp="0"
ipaddr="192.168.108.4"
rtsp_auth_en="0"
rtmp1_en="1"
rtmp1_mrl="rtmps://x.rtmp.youtube.com/live2/FAKE-test-key-aaaa-bbbb"
rtmp1_video_en="1"
rtmp2_en="0"
rtmp2_mrl="rtmp://192.168.100.138/live/stream1"
'''


def ident(a):
    return a['WFWorkflowActionIdentifier'].split('is.workflow.actions.')[-1]


def params(a):
    return a['WFWorkflowActionParameters']


def url_string(a):
    return params(a)['WFURL']['Value']['string']


def walk(obj):
    """Yield every dict nested anywhere in a JSON-like structure."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def match_action():
    return next(a for a in ACTS if a['WFWorkflowActionIdentifier'].endswith('text.match'))


def if_starts():
    return [params(a) for a in ACTS
            if ident(a) == 'conditional' and params(a).get('WFControlFlowMode') == 0]


class TokenTests(unittest.TestCase):
    def test_literal_only_has_no_attachments(self):
        t = build.token(['http://example/x'])
        self.assertEqual(t['Value']['string'], 'http://example/x')
        self.assertNotIn('attachmentsByRange', t['Value'])

    def test_single_attachment_offset(self):
        t = build.token(['http://', ('var', 'ip'), '/x'])
        self.assertEqual(t['Value']['string'], 'http://￼/x')
        att = t['Value']['attachmentsByRange']
        self.assertEqual(list(att), ['{7, 1}'])
        self.assertEqual(att['{7, 1}'], {'Type': 'Variable', 'VariableName': 'ip'})

    def test_two_attachment_offsets(self):
        t = build.token([('var', 'a'), 'X', ('var', 'b')])
        self.assertEqual(t['Value']['string'], '￼X￼')
        self.assertEqual(set(t['Value']['attachmentsByRange']), {'{0, 1}', '{2, 1}'})

    def test_action_output_segment(self):
        t = build.token([('out', 'Matches', 'UUID-1')])
        att = t['Value']['attachmentsByRange']['{0, 1}']
        self.assertEqual(att, {'Type': 'ActionOutput',
                               'OutputName': 'Matches', 'OutputUUID': 'UUID-1'})


class TopLevelTests(unittest.TestCase):
    def test_required_metadata_keys_present(self):
        for k in ('WFWorkflowActions', 'WFWorkflowImportQuestions',
                  'WFWorkflowIcon', 'WFWorkflowClientVersion'):
            self.assertIn(k, OUT)

    def test_plist_serializable_and_roundtrips(self):
        data = plistlib.dumps(OUT, fmt=plistlib.FMT_BINARY)
        back = plistlib.loads(data)
        self.assertEqual(len(back['WFWorkflowActions']), len(ACTS))


class MenuTests(unittest.TestCase):
    def test_exact_menu_items(self):
        starts = [a for a in ACTS
                  if ident(a) == 'choosefrommenu' and params(a).get('WFControlFlowMode') == 0]
        self.assertEqual(len(starts), 1)
        self.assertEqual(params(starts[0])['WFMenuItems'],
                         ['Move Camera', 'Start Camera', 'Stop Camera'])

    def test_no_go_home(self):
        titles = [params(a).get('WFMenuItemTitle') for a in ACTS if ident(a) == 'choosefrommenu']
        self.assertNotIn('Go Home', titles)


class ImportQuestionTests(unittest.TestCase):
    def setUp(self):
        self.qs = OUT['WFWorkflowImportQuestions']

    def test_three_questions(self):
        self.assertEqual(len(self.qs), 3)

    def test_preset_map_is_not_prompted(self):
        self.assertFalse(any(q['ParameterKey'] == 'WFItems' for q in self.qs))

    def test_indices_point_at_correct_config_keys(self):
        seen = set()
        for q in self.qs:
            a = ACTS[q['ActionIndex']]
            self.assertEqual(ident(a), 'setvalueforkey')
            self.assertEqual(q['ParameterKey'], 'WFDictionaryValue')
            seen.add(params(a)['WFDictionaryKey'])
        self.assertEqual(seen, {'cameraIP', 'streamURL', 'streamKey'})


class ControlFlowTests(unittest.TestCase):
    def test_every_group_opens_and_closes_once(self):
        groups = defaultdict(list)
        for a in ACTS:
            p = params(a)
            if 'GroupingIdentifier' in p:
                groups[p['GroupingIdentifier']].append(p.get('WFControlFlowMode'))
        self.assertTrue(groups)
        for gid, modes in groups.items():
            self.assertEqual(modes.count(0), 1, f'group {gid} must start once')
            self.assertEqual(modes.count(2), 1, f'group {gid} must end once')
            self.assertEqual(modes[0], 0, f'group {gid} must start first')
            self.assertEqual(modes[-1], 2, f'group {gid} must end last')


class MoveCameraTests(unittest.TestCase):
    def test_poscall_url_built_from_ip_and_preset(self):
        gets = [a for a in ACTS if ident(a) == 'downloadurl'
                and params(a)['WFHTTPMethod'] == 'GET' and 'poscall' in url_string(a)]
        self.assertEqual(len(gets), 1)
        att = params(gets[0])['WFURL']['Value']['attachmentsByRange']
        kinds = {(v.get('VariableName') or v.get('OutputName')) for v in att.values()}
        self.assertIn('cameraIP', kinds)
        self.assertIn('Dictionary Value', kinds)


class StreamCombineTests(unittest.TestCase):
    def test_streamMRL_is_url_slash_key(self):
        gt = next(a for a in ACTS if ident(a) == 'gettext')
        val = params(gt)['WFTextActionText']['Value']
        self.assertEqual(val['string'], '￼/￼')
        names = [v['VariableName'] for v in val['attachmentsByRange'].values()]
        self.assertEqual(names, ['streamURL', 'streamKey'])

    def test_start_form_posts_streamMRL_for_rtmp1_mrl(self):
        forms = [params(a) for a in ACTS if ident(a) == 'downloadurl'
                 and params(a).get('WFHTTPBodyType') == 'Form'
                 and 'post_network_other_conf' in url_string(a)]
        on_forms = [f for f in forms if self._field(f, 'rtmp1') == 'on']
        self.assertTrue(on_forms)
        for f in on_forms:
            mrl = self._field_token(f, 'rtmp1_mrl')
            ref = next(iter(mrl['Value']['attachmentsByRange'].values()))
            self.assertEqual(ref['VariableName'], 'streamMRL')

    def test_stop_form_turns_rtmp1_off(self):
        forms = [params(a) for a in ACTS if ident(a) == 'downloadurl'
                 and params(a).get('WFHTTPBodyType') == 'Form'
                 and 'post_network_other_conf' in url_string(a)]
        self.assertTrue(any(self._field(f, 'rtmp1') == 'off' for f in forms))

    def _field_token(self, form, key):
        for it in form['WFFormValues']['Value']['WFDictionaryFieldValueItems']:
            if it['WFKey']['Value']['string'] == key:
                return it['WFValue']
        return None

    def _field(self, form, key):
        tok = self._field_token(form, key)
        return tok['Value']['string'] if tok else None


class StartStreamGuardTests(unittest.TestCase):
    def test_reads_network_conf_before_starting(self):
        gets = [url_string(a) for a in ACTS
                if ident(a) == 'downloadurl' and params(a)['WFHTTPMethod'] == 'GET']
        self.assertTrue(any('get_network_conf' in u for u in gets))

    def test_match_pattern_is_present(self):
        self.assertEqual(params(match_action())['WFMatchTextPattern'], r'(?<=rtmp1_mrl=")[^"]+')

    def test_guard_compares_currentMRL_to_streamMRL_and_empty(self):
        compared_vars, compared_literals = set(), set()
        for p in if_starts():
            self.assertEqual(p['WFCondition'], 4)  # 4 == "Is"
            self.assertEqual(p['WFInput']['Variable']['Value']['VariableName'], 'currentMRL')
            s = p['WFConditionalActionString']['Value']
            if 'attachmentsByRange' in s:
                compared_vars.add(next(iter(s['attachmentsByRange'].values()))['VariableName'])
            else:
                compared_literals.add(s['string'])
        self.assertIn('streamMRL', compared_vars)   # case (b): exact match
        self.assertIn('', compared_literals)        # case (a): no URL set

    def test_mismatch_path_alerts(self):
        self.assertTrue(any(ident(a) == 'alert' for a in ACTS))


class MatchRegexBehaviorTests(unittest.TestCase):
    """The build's regex is ICU-flavored; Python `re` supports the same
    fixed-length lookbehind, so we can validate extraction behavior here."""
    def setUp(self):
        self.pat = params(match_action())['WFMatchTextPattern']

    def test_extracts_configured_mrl(self):
        self.assertEqual(re.findall(self.pat, SAMPLE_CONF),
                         ['rtmps://x.rtmp.youtube.com/live2/FAKE-test-key-aaaa-bbbb'])

    def test_no_match_when_unset(self):
        self.assertEqual(re.findall(self.pat, 'rtmp1_mrl=""\nrtmp1_en="0"\n'), [])

    def test_does_not_grab_rtmp2(self):
        found = re.findall(self.pat, SAMPLE_CONF)
        self.assertNotIn('rtmp://192.168.100.138/live/stream1', found)


class ReferenceIntegrityTests(unittest.TestCase):
    def test_every_action_output_ref_resolves(self):
        uuids = {params(a).get('UUID') for a in ACTS} - {None}
        for d in walk(OUT):
            if d.get('Type') == 'ActionOutput':
                self.assertIn(d['OutputUUID'], uuids,
                              f"dangling ActionOutput {d.get('OutputName')!r}")

    def test_every_variable_ref_is_defined(self):
        defined = {params(a)['WFVariableName'] for a in ACTS if ident(a) == 'setvariable'}
        for d in walk(OUT):
            if d.get('Type') == 'Variable' and d.get('VariableName'):
                self.assertIn(d['VariableName'], defined,
                              f"undefined variable {d['VariableName']!r}")

    def test_uuids_are_unique(self):
        uuids = [params(a)['UUID'] for a in ACTS if 'UUID' in params(a)]
        dupes = [u for u, n in Counter(uuids).items() if n > 1]
        self.assertEqual(dupes, [], f'duplicate UUIDs: {dupes}')


if __name__ == '__main__':
    unittest.main()
