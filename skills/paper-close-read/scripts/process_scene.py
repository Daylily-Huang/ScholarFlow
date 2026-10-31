"""Validate declarative drawings and the authored explanation coverage plan.

Only bounded data is accepted; there are no expressions, scripts or external assets.
Content adequacy and source support still require an actual editorial/browser review.
"""
import math
import re

NUMBERS = {'x', 'y', 'x2', 'y2', 'w', 'h', 'r', 'opacity', 'font_size', 'line_width'}
PROPERTIES = NUMBERS | {'fill', 'stroke', 'text', 'points', 'align'}
REQUIRED = {'circle': {'x', 'y', 'r'}, 'rect': {'x', 'y', 'w', 'h'},
            'line': {'x', 'y', 'x2', 'y2'}, 'polyline': {'points'}, 'text': {'x', 'y', 'text'}}


def validate_process(visual):
    errors = []
    if not isinstance(visual, dict):
        return ['Process visual must be an object']
    if set(visual) - {'description', 'elements'}:
        errors.append('Unknown process visual property')
    if not isinstance(visual.get('description'), str) or not visual['description'].strip():
        errors.append('Process needs a description of objects, conditions and teaching values')
    elements = visual.get('elements')
    if not isinstance(elements, list) or not 1 <= len(elements) <= 100:
        return errors + ['Process needs 1–100 elements']
    ids = set()
    substantive_change = False

    def props(value, label):
        if not isinstance(value, dict):
            errors.append(label + ' must be an object'); return
        for key, v in value.items():
            if key not in PROPERTIES:
                errors.append(label + ': unknown property ' + key)
            elif key in NUMBERS:
                bound = 1 if key == 'opacity' else 48 if key == 'font_size' else 20 if key == 'line_width' else 900
                if type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= bound or (key == 'font_size' and v < 10):
                    errors.append(label + ': invalid number ' + key)
            elif key in {'fill', 'stroke'}:
                if not isinstance(v, str) or not re.fullmatch(r'none|#[0-9a-fA-F]{6}', v):
                    errors.append(label + ': use none or a six-digit hex color')
            elif key == 'text':
                if not isinstance(v, str) or len(v) > 240:
                    errors.append(label + ': text must be at most 240 characters')
            elif key == 'align':
                if v not in ('left', 'center', 'right'):
                    errors.append(label + ': invalid text alignment')
            elif key == 'points':
                if not isinstance(v, list) or not 2 <= len(v) <= 200 or any(
                    not isinstance(p, list) or len(p) != 2 or any(type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 900 for n in p) for p in v):
                    errors.append(label + ': points need 2–200 bounded coordinate pairs')

    for n, el in enumerate(elements):
        label = 'Process element ' + str(n)
        if not isinstance(el, dict):
            errors.append(label + ' must be an object'); continue
        if set(el) - {'id', 'type', 'meaning', 'props', 'frames'}:
            errors.append(label + ': unknown field')
        eid = el.get('id')
        if not isinstance(eid, str) or not eid or eid in ids:
            errors.append(label + ': needs unique id')
        if isinstance(eid, str): ids.add(eid)
        kind = el.get('type')
        if not isinstance(kind, str) or kind not in REQUIRED:
            errors.append(label + ': unknown drawing type'); continue
        if not isinstance(el.get('meaning'), str) or not el['meaning'].strip():
            errors.append(label + ': needs its meaning in the explanation')
        base = el.get('props')
        props(base, label)
        if not isinstance(base, dict): continue
        if not REQUIRED[kind] <= set(base): errors.append(label + ': missing geometry/text')
        frames = el.get('frames', [])
        if not isinstance(frames, list) or len(frames) > 50:
            errors.append(label + ': frames must be an array of at most 50 entries'); continue
        previous = -1
        state = dict(base)
        for frame in frames:
            if not isinstance(frame, dict):
                errors.append(label + ': frame must be an object'); continue
            at = frame.get('at')
            if type(at) not in (int, float) or not math.isfinite(at) or not 0 <= at <= 1 or at <= previous:
                errors.append(label + ': frame times must increase strictly from 0 to 1')
            else: previous = at
            changes = {k: v for k, v in frame.items() if k != 'at'}
            props(changes, label + ' frame')
            if 'points' in changes and isinstance(base.get('points'), list) and isinstance(changes['points'], list) and len(changes['points']) != len(base['points']):
                errors.append(label + ': animated polylines need matching point counts')
            # Opacity/text changes alone do not demonstrate a process. Geometry or
            # a visible object-state (fill) change is required, with meaning reviewed.
            if kind != 'text' and any(k in changes and changes[k] != state.get(k) for k in {'x', 'y', 'x2', 'y2', 'w', 'h', 'r', 'points', 'fill'}):
                substantive_change = True
            state.update(changes)
    if not substantive_change:
        errors.append('Process needs a non-text object changing geometry or state; text/opacity-only slides are not a process')
    return errors


def validate_visual_plan(guide, source_ids, required=False):
    plan = guide.get('visual_plan')
    if plan is None:
        return ['New complete readers require visual_plan'] if required else []
    if not isinstance(plan, list) or not plan:
        return ['visual_plan must be a nonempty array; explain text/static choices too']
    errors, used = [], set()
    motions = {m['id']: m for m in guide.get('mechanisms', [])
               if isinstance(m, dict) and isinstance(m.get('id'), str)}
    inline = {m['id'] for c in guide.get('story', {}).get('walkthrough', []) for m in c.get('motions', [])
              if isinstance(m, dict) and isinstance(m.get('id'), str)}
    covered = set()
    for item in plan:
        if not isinstance(item, dict):
            errors.append('visual_plan entry must be an object'); continue
        for k in ('id', 'question', 'reason', 'observe'):
            if not isinstance(item.get(k), str) or not item[k].strip(): errors.append('visual_plan needs text: ' + k)
        pid = item.get('id')
        if isinstance(pid, str):
            if pid in used: errors.append('Duplicate visual_plan id')
            used.add(pid)
        refs = item.get('refs')
        if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or r not in source_ids for r in refs):
            errors.append('visual_plan needs valid source refs')
        mode = item.get('mode')
        if mode not in ('motion', 'figure', 'static', 'text'):
            errors.append('Unknown visual_plan mode')
        if mode == 'motion':
            mid = item.get('mechanism')
            if not isinstance(mid, str) or mid not in motions or mid not in inline:
                errors.append('visual_plan motion must exist and be embedded in walkthrough'); continue
            covered.add(mid)
            if item.get('kind') not in ('mechanism', 'argument'):
                errors.append('visual_plan motion kind must be mechanism or argument')
            if item.get('kind') == 'mechanism' and motions[mid].get('scene') == 'argument_map':
                errors.append('An argument_map cannot stand in for a mechanism demonstration')
    if required and set(motions) - covered:
        errors.append('Every independent mechanism needs a visual_plan entry; duplicate players do not add coverage')
    return errors
