#!/usr/bin/env python3
"""Build a Camera Control shortcut for the RL500 PTZ camera.

Reuses the exact WFSerialization patterns observed in the original AIDA
shortcut (shortcut.json) so the output imports cleanly into Shortcuts.
"""
import json, os, plistlib, uuid

HERE = os.path.dirname(os.path.abspath(__file__))   # src/
ROOT = os.path.dirname(HERE)                         # repo root
DIST = os.path.join(ROOT, 'dist')                    # generated output

U = lambda: str(uuid.uuid4()).upper()

# ---- text-token helpers -------------------------------------------------
def attach(seg):
    kind = seg[0]
    if kind == 'var':
        return {'Type': 'Variable', 'VariableName': seg[1]}
    if kind == 'varkey':
        return {'Type': 'Variable', 'VariableName': seg[1],
                'Aggrandizements': [{'DictionaryKey': seg[2],
                                     'Type': 'WFDictionaryValueVariableAggrandizement'}]}
    if kind == 'out':
        return {'Type': 'ActionOutput', 'OutputName': seg[1], 'OutputUUID': seg[2]}
    raise ValueError(seg)

def token(segments):
    """segments: list of str (literal) or tuples (var/varkey/out)."""
    s, att = '', {}
    for seg in segments:
        if isinstance(seg, str):
            s += seg
        else:
            att['{%d, 1}' % len(s)] = attach(seg)
            s += '￼'
    val = {'string': s}
    if att:
        val['attachmentsByRange'] = att
    return {'Value': val, 'WFSerializationType': 'WFTextTokenString'}

def dict_field(value):
    return {'Value': value, 'WFSerializationType': 'WFDictionaryFieldValue'}

def text_item(key, value_token):
    return {'WFItemType': 3,
            'WFKey': {'Value': {'string': key}, 'WFSerializationType': 'WFTextTokenString'},
            'WFValue': value_token}

def action(ident, params):
    return {'WFWorkflowActionIdentifier': 'is.workflow.actions.' + ident,
            'WFWorkflowActionParameters': params}

# ---- UUIDs we need to reference later -----------------------------------
PRESETS_DICT = U()          # dictionary action that defines the preset map
CFG_DICT     = U()          # empty dictionary that seeds the config
SV_IP        = U()          # setvalueforkey cameraIP
SV_URL       = U()          # setvalueforkey streamURL
SV_KEY       = U()          # setvalueforkey streamKey
TEXT_MRL     = U()          # text action that joins URL + key
LIST         = U()          # choosefromlist (preset names)
GETVAL       = U()          # getvalueforkey -> preset number
NET_GET      = U()          # GET get_network_conf (read current camera config)
MATCH        = U()          # match text -> current rtmp1_mrl value
GRP_A        = U()          # outer guard conditional (exact-match case)
GRP_B        = U()          # inner guard conditional (empty / mismatch case)
MENU_GROUP   = U()
MENU_END     = U()

CAMERA_IP_DEFAULT  = '192.168.108.4'
# YouTube gives these as two separate fields; the shortcut joins them as URL/key.
STREAM_URL_DEFAULT = 'rtmps://a.rtmp.youtube.com/live2'
STREAM_KEY_DEFAULT = 'xxxx-xxxx-xxxx-xxxx-xxxx'

PRESETS = [('Pulpit', '0'), ('Choir', '1'), ('Congregation', '2'),
           ('Organ', '3'), ('Piano', '4')]

actions = []
idx = {}   # records action indices that import questions point at

# 0) credit / description comment
actions.append(action('comment', {'WFCommentActionText':
    'Camera Control for the RL500 PTZ camera. Adapted from Ryan Okelberry\'s '
    'original AIDA shortcut. On import you will be asked for the camera IP and the '
    'YouTube Stream URL and Stream Key (joined automatically).'}))

# 1) presets dictionary  (preset name -> preset number; configured here, not at import,
#    because the mapping is fixed by how the camera's presets are saved)
actions.append(action('dictionary', {
    'UUID': PRESETS_DICT,
    'WFItems': dict_field({'WFDictionaryFieldValueItems': [
        text_item(name, {'Value': {'string': num}, 'WFSerializationType': 'WFTextTokenString'})
        for name, num in PRESETS]})}))

# 2) set variable "presets"
actions.append(action('setvariable', {
    'WFVariableName': 'presets',
    'WFInput': {'Value': {'OutputName': 'Dictionary', 'OutputUUID': PRESETS_DICT,
                          'Type': 'ActionOutput'},
                'WFSerializationType': 'WFTextTokenAttachment'}}))

# 3) empty config dictionary
actions.append(action('dictionary', {'UUID': CFG_DICT}))

# 4) setvalueforkey cameraIP  (import question -> WFDictionaryValue)
idx['cameraIP'] = len(actions)
actions.append(action('setvalueforkey', {
    'UUID': SV_IP,
    'WFDictionary': {'Value': {'OutputName': 'Dictionary', 'OutputUUID': CFG_DICT,
                               'Type': 'ActionOutput'},
                     'WFSerializationType': 'WFTextTokenAttachment'},
    'WFDictionaryKey': 'cameraIP',
    'WFDictionaryValue': CAMERA_IP_DEFAULT}))

# 5) setvalueforkey streamURL  (import question -> WFDictionaryValue)
idx['streamURL'] = len(actions)
actions.append(action('setvalueforkey', {
    'UUID': SV_URL,
    'WFDictionary': {'Value': {'OutputName': 'Dictionary', 'OutputUUID': SV_IP,
                               'Type': 'ActionOutput'},
                     'WFSerializationType': 'WFTextTokenAttachment'},
    'WFDictionaryKey': 'streamURL',
    'WFDictionaryValue': STREAM_URL_DEFAULT}))

# 6) setvalueforkey streamKey  (import question -> WFDictionaryValue)
idx['streamKey'] = len(actions)
actions.append(action('setvalueforkey', {
    'UUID': SV_KEY,
    'WFDictionary': {'Value': {'OutputName': 'Dictionary', 'OutputUUID': SV_URL,
                               'Type': 'ActionOutput'},
                     'WFSerializationType': 'WFTextTokenAttachment'},
    'WFDictionaryKey': 'streamKey',
    'WFDictionaryValue': STREAM_KEY_DEFAULT}))

# 7) set variable "config"
actions.append(action('setvariable', {
    'WFVariableName': 'config',
    'WFInput': {'Value': {'OutputName': 'Dictionary', 'OutputUUID': SV_KEY,
                          'Type': 'ActionOutput'},
                'WFSerializationType': 'WFTextTokenAttachment'}}))

# 7) cameraIP variable  <- config[cameraIP]
def from_config(var, key):
    return action('setvariable', {
        'WFVariableName': var,
        'WFInput': {'Value': {'Aggrandizements': [
                        {'DictionaryKey': key, 'Type': 'WFDictionaryValueVariableAggrandizement'}],
                    'Type': 'Variable', 'VariableName': 'config'},
                    'WFSerializationType': 'WFTextTokenAttachment'}})
actions.append(from_config('cameraIP', 'cameraIP'))
actions.append(from_config('streamURL', 'streamURL'))
actions.append(from_config('streamKey', 'streamKey'))

# Combine the YouTube Stream URL + Stream Key into a single RTMP URL:
#   {streamURL}/{streamKey}  ->  variable "streamMRL"
actions.append(action('gettext', {
    'UUID': TEXT_MRL,
    'WFTextActionText': token([('var', 'streamURL'), '/', ('var', 'streamKey')])}))
actions.append(action('setvariable', {
    'WFVariableName': 'streamMRL',
    'WFInput': {'Value': {'OutputName': 'Text', 'OutputUUID': TEXT_MRL,
                          'Type': 'ActionOutput'},
                'WFSerializationType': 'WFTextTokenAttachment'}}))

# menu START
actions.append(action('choosefrommenu', {
    'GroupingIdentifier': MENU_GROUP, 'WFControlFlowMode': 0,
    'WFMenuPrompt': 'Camera Control',
    'WFMenuItems': ['Move Camera', 'Start Camera', 'Stop Camera']}))

def menu_case(title):
    return action('choosefrommenu', {'GroupingIdentifier': MENU_GROUP,
                                      'WFControlFlowMode': 1, 'WFMenuItemTitle': title})

def get_url(url_segments, uuid_=None):
    p = {'WFHTTPMethod': 'GET', 'WFURL': token(url_segments)}
    if uuid_: p['UUID'] = uuid_
    return action('downloadurl', p)

def post_form(url_segments, fields):
    return action('downloadurl', {
        'UUID': U(), 'WFHTTPMethod': 'POST', 'WFHTTPBodyType': 'Form',
        'WFURL': token(url_segments),
        'WFFormValues': dict_field({'WFDictionaryFieldValueItems':
            [text_item(k, v) for k, v in fields]})})

def match_text(text_token, pattern, uuid_):
    return action('text.match', {'UUID': uuid_, 'WFMatchTextPattern': pattern,
                                 'text': text_token})

def _cond_input(var):   # a variable input, coerced to string for comparison
    return {'Type': 'Variable',
            'Variable': {'Value': {'Aggrandizements': [
                            {'CoercionItemClass': 'WFStringContentItem',
                             'Type': 'WFCoercionVariableAggrandizement'}],
                         'Type': 'Variable', 'VariableName': var},
                         'WFSerializationType': 'WFTextTokenAttachment'}}

def if_equals(group, var, compare_token):   # WFCondition 4 == "Is"
    return action('conditional', {'GroupingIdentifier': group, 'WFCondition': 4,
                                  'WFControlFlowMode': 0, 'WFInput': _cond_input(var),
                                  'WFConditionalActionString': compare_token})

def otherwise(group):
    return action('conditional', {'GroupingIdentifier': group, 'WFControlFlowMode': 1})

def end_if(group):
    return action('conditional', {'GroupingIdentifier': group, 'UUID': U(),
                                  'WFControlFlowMode': 2})

def alert(message_token):
    return action('alert', {'WFAlertActionCancelButtonShown': False,
                            'WFAlertActionMessage': message_token})

PTZ = '/cgi-bin/ptzctrl.cgi?ptzcmd&'
PARAM = '/cgi-bin/param.cgi?post_network_other_conf'
CONF = '/cgi-bin/param.cgi?get_network_conf'

# --- CASE: Move Camera ---
actions.append(menu_case('Move Camera'))
# choose a preset name from the presets dictionary keys
actions.append(action('choosefromlist', {
    'UUID': LIST,
    'WFInput': {'Value': {'Aggrandizements': [{'PropertyName': 'Keys',
                          'Type': 'WFPropertyVariableAggrandizement'}],
                'Type': 'Variable', 'VariableName': 'presets'},
                'WFSerializationType': 'WFTextTokenAttachment'}}))
# map the chosen name -> preset number
actions.append(action('getvalueforkey', {
    'UUID': GETVAL,
    'WFInput': {'Value': {'Type': 'Variable', 'VariableName': 'presets'},
                'WFSerializationType': 'WFTextTokenAttachment'},
    'WFDictionaryKey': token([('out', 'Chosen Item', LIST)])}))
# GET poscall
actions.append(get_url(['http://', ('var', 'cameraIP'), PTZ + 'poscall&',
                        ('out', 'Dictionary Value', GETVAL)]))

# --- CASE: Start Camera (guarded) ---
def start_stream():
    return post_form(['http://', ('var', 'cameraIP'), PARAM], [
        ('rtmp1', token(['on'])),
        ('rtmp1_mrl', token([('var', 'streamMRL')])),
        ('rtmp1video', token(['on'])),
        ('rtmp1audio', token(['on']))])

actions.append(menu_case('Start Camera'))
# Read the camera's current network/stream config (plain key="value" lines)...
actions.append(get_url(['http://', ('var', 'cameraIP'), CONF], uuid_=NET_GET))
# ...and pull out the rtmp1 destination currently loaded on the camera (URL + key).
actions.append(match_text(token([('out', 'Contents of URL', NET_GET)]),
                          r'(?<=rtmp1_mrl=")[^"]+', MATCH))
actions.append(action('setvariable', {
    'WFVariableName': 'currentMRL',
    'WFInput': {'Value': {'OutputName': 'Matches', 'OutputUUID': MATCH, 'Type': 'ActionOutput'},
                'WFSerializationType': 'WFTextTokenAttachment'}}))

# Guard: only start if the camera is free (no URL set) OR already set to OUR destination.
# (b) currentMRL == our combined URL+key -> safe to (re)start
actions.append(if_equals(GRP_A, 'currentMRL', token([('var', 'streamMRL')])))
actions.append(start_stream())
actions.append(otherwise(GRP_A))
#   (a) currentMRL is empty -> no stream configured, safe to start
actions.append(if_equals(GRP_B, 'currentMRL', token([''])))
actions.append(start_stream())
actions.append(otherwise(GRP_B))
#   else: a *different* destination is loaded -> refuse, don't clobber another group's key
actions.append(alert(token([
    'The camera is already configured to stream to a different destination:\n',
    ('var', 'currentMRL'),
    '\n\nStart cancelled so another group’s stream key is not overwritten.'])))
actions.append(end_if(GRP_B))
actions.append(end_if(GRP_A))

# --- CASE: Stop Camera ---
actions.append(menu_case('Stop Camera'))
actions.append(post_form(['http://', ('var', 'cameraIP'), PARAM], [
    ('rtmp1', token(['off']))]))

# menu END
actions.append(action('choosefrommenu', {'GroupingIdentifier': MENU_GROUP,
                                          'UUID': MENU_END, 'WFControlFlowMode': 2}))

# ---- assemble, copying metadata from the original ----------------------
# original.plist is the untouched shortcut downloaded from iCloud; we read it
# only to reuse its icon / version / supported-input metadata. Never edited.
orig = plistlib.load(open(os.path.join(HERE, 'original.plist'), 'rb'))
out = {}
for k in ['WFQuickActionSurfaces', 'WFWorkflowClientVersion', 'WFWorkflowHasOutputFallback',
          'WFWorkflowHasShortcutInputVariables', 'WFWorkflowIcon',
          'WFWorkflowInputContentItemClasses', 'WFWorkflowMinimumClientVersion',
          'WFWorkflowMinimumClientVersionString', 'WFWorkflowOutputContentItemClasses',
          'WFWorkflowTypes']:
    if k in orig:
        out[k] = orig[k]

out['WFWorkflowActions'] = actions

# import questions (indices captured dynamically in `idx` as actions were built)
out['WFWorkflowImportQuestions'] = [
    {'ActionIndex': idx['cameraIP'], 'Category': 'Parameter', 'ParameterKey': 'WFDictionaryValue',
     'Text': 'What is the camera IP address?', 'DefaultValue': CAMERA_IP_DEFAULT},
    {'ActionIndex': idx['streamURL'], 'Category': 'Parameter', 'ParameterKey': 'WFDictionaryValue',
     'Text': 'What is your YouTube Stream URL? (e.g. rtmps://a.rtmp.youtube.com/live2)',
     'DefaultValue': STREAM_URL_DEFAULT},
    {'ActionIndex': idx['streamKey'], 'Category': 'Parameter', 'ParameterKey': 'WFDictionaryValue',
     'Text': 'What is your YouTube Stream Key?', 'DefaultValue': STREAM_KEY_DEFAULT},
]

# Importing this module builds `out` (with no side effects) so tests can inspect it;
# only writing the file happens when run as a script.
if __name__ == '__main__':
    os.makedirs(DIST, exist_ok=True)
    out_path = os.path.join(DIST, 'rl500.json')
    json.dump(out, open(out_path, 'w'), indent=1)
    print('wrote', os.path.relpath(out_path, ROOT), 'with', len(actions), 'actions')
