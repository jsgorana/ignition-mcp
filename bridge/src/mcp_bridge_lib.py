# mcp_bridge_lib — project script library holding ALL bridge logic (Jython 2.7).
# The WebDev python resource "api" is a one-liner delegating here:
#   def doPost(request, session): return mcp_bridge_lib.handle(request)
# Mounted at: POST /system/webdev/mcp-bridge/api/<endpoint>
#
# Request body is a signed envelope produced by ignition-mcp's BridgeClient:
#   {"ts": "<unix seconds>", "sig": hex hmac-sha256(secret, ts + "." + payload),
#    "payload": "<json string>"}
#
# SECURITY-CRITICAL FILE — hand-written and reviewed. Handler functions below the
# dispatch table are generated against the handler contract in tasks/context/webdev.md.

import hashlib
import hmac
import os
import codecs

BRIDGE_VERSION = '0.1.0'

# Set at install time (bridge_install rewrites this constant, or edit manually).
BRIDGE_SECRET = '__BRIDGE_SECRET__'

MAX_SKEW_SECONDS = 300

LOGGER = system.util.getLogger('mcp-bridge')

PROJECTS_ROOT = os.path.abspath(
    os.path.join(system.util.getProperty('user.dir'), 'data', 'projects'))


# --------------------------------------------------------------------- helpers

def _err(message, remediation=''):
    return {'__error__': True, 'error': str(message), 'remediation': remediation}


def _is_err(result):
    return isinstance(result, dict) and result.get('__error__') is True


def _fmt_date(java_date):
    if java_date is None:
        return None
    try:
        return system.date.format(java_date, 'yyyy-MM-dd HH:mm:ss')
    except Exception:
        return str(java_date)


def _parse_when(s):
    """ISO 'yyyy-MM-ddTHH:mm:ss', relative '-8h'/'-30m'/'-2d', or '' (= now)."""
    if not s:
        return system.date.now()
    s = s.strip()
    if s.startswith('-') and len(s) >= 3 and s[-1] in ('m', 'h', 'd'):
        try:
            amount = int(s[1:-1])
        except ValueError:
            raise ValueError('bad relative time: %s' % s)
        unit = s[-1]
        now = system.date.now()
        if unit == 'm':
            return system.date.addMinutes(now, -amount)
        if unit == 'h':
            return system.date.addHours(now, -amount)
        return system.date.addDays(now, -amount)
    iso = s.replace('T', ' ')
    if len(iso) == 10:
        iso = iso + ' 00:00:00'
    return system.date.parse(iso, 'yyyy-MM-dd HH:mm:ss')


def _json_safe(value):
    if value is None or isinstance(value, (int, long, float, bool, str, unicode)):
        return value
    try:
        return _fmt_date(value)
    except Exception:
        return str(value)


def _ds_to_table(dataset):
    columns = [str(dataset.getColumnName(c)) for c in range(dataset.getColumnCount())]
    rows = []
    for r in range(dataset.getRowCount()):
        rows.append([_json_safe(dataset.getValueAt(r, c)) for c in range(len(columns))])
    return {'columns': columns, 'rows': rows}


def _safe_path(rel):
    """Resolve a path relative to PROJECTS_ROOT; refuse traversal outside it."""
    if not rel or rel.startswith('/') or rel.startswith('\\'):
        raise ValueError('path must be relative: %s' % rel)
    resolved = os.path.abspath(os.path.join(PROJECTS_ROOT, rel))
    if not (resolved == PROJECTS_ROOT or resolved.startswith(PROJECTS_ROOT + os.sep)):
        raise ValueError('path escapes data/projects: %s' % rel)
    return resolved


def _compare_digest(a, b):
    try:
        return hmac.compare_digest(a, b)
    except AttributeError:
        if len(a) != len(b):
            return False
        result = 0
        for x, y in zip(a, b):
            result |= ord(x) ^ ord(y)
        return result == 0


def _verify(envelope):
    """Returns (payload_dict, None) on success, (None, http_response_dict) on failure."""
    def reject():
        return {'json': {'ok': False, 'code': 'auth', 'error': 'authentication failed'}}

    if BRIDGE_SECRET == '__BRIDGE_SECRET__':
        return None, {'json': {'ok': False, 'code': 'auth',
                               'error': 'bridge secret not configured',
                               'remediation': 'Set BRIDGE_SECRET in the mcp-bridge api resource.'}}
    if not isinstance(envelope, dict):
        return None, reject()
    ts = envelope.get('ts')
    sig = envelope.get('sig')
    payload_str = envelope.get('payload')
    if not ts or not sig or payload_str is None:
        return None, reject()
    try:
        skew = abs(system.date.toMillis(system.date.now()) / 1000 - long(ts))
    except Exception:
        return None, reject()
    if skew > MAX_SKEW_SECONDS:
        return None, reject()
    if isinstance(payload_str, unicode):
        payload_bytes = payload_str.encode('utf-8')
    else:
        payload_bytes = str(payload_str)
    message = str(ts) + '.' + payload_bytes
    expected = hmac.new(str(BRIDGE_SECRET), message, hashlib.sha256).hexdigest()
    if not _compare_digest(str(expected), str(sig)):
        return None, reject()
    try:
        payload = system.util.jsonDecode(payload_str)
    except Exception:
        return None, {'json': {'ok': False, 'error': 'payload is not valid JSON'}}
    return payload or {}, None


# ------------------------------------------------------------------- handlers

def handle_ping(payload):
    return {'version': BRIDGE_VERSION,
            'capabilities': sorted(HANDLERS.keys())}


# Generated handlers are inserted below this line (see tasks/010-013). ----------

def handle_tags_browse(payload):
    path = payload.get('path') or ''
    provider = payload.get('provider') or 'default'
    depth = int(payload.get('depth') or 1)
    root = '[%s]%s' % (provider, path)

    def _browse(browse_path, level):
        results = system.tag.browse(browse_path).getResults()
        nodes = []
        for r in results:
            node = {
                'fullPath': str(r['fullPath']),
                'name': str(r['name']),
                'tagType': str(r['tagType']),
                'dataType': str(r.get('dataType')) if r.get('dataType') else None,
                'hasChildren': bool(r['hasChildren'])
            }
            if r['hasChildren'] and level < depth:
                node['children'] = _browse(str(r['fullPath']), level + 1)
            nodes.append(node)
        return nodes

    return {'results': _browse(root, 1)}

def handle_tags_read(payload):
    paths = payload.get('paths') or []
    if not paths:
        return _err('paths is required')
    values = system.tag.readBlocking(paths)
    tags = []
    for i in range(len(paths)):
        tags.append({
            'path': paths[i],
            'value': _json_safe(values[i].value),
            'quality': str(values[i].quality),
            'timestamp': _fmt_date(values[i].timestamp)
        })
    return {'tags': tags}

def handle_tags_write(payload):
    writes = payload.get('writes') or []
    if not writes:
        return _err('writes is required')
    paths = [w['path'] for w in writes]
    values = [w['value'] for w in writes]
    results = system.tag.writeBlocking(paths, values)
    tags = []
    for i in range(len(paths)):
        tags.append({
            'path': paths[i],
            'quality': str(results[i])
        })
    return {'results': tags}

def handle_tags_configure(payload):
    base_path = payload.get('basePath') or '[default]'
    tags = payload.get('tags') or []
    if not tags:
        return _err('tags is required')
    policy = payload.get('collisionPolicy') or 'a'
    results = system.tag.configure(base_path, tags, policy)
    return {'results': [str(qc) for qc in results]}


def handle_history_query(payload):
    paths = payload.get('paths') or []
    if not paths:
        return _err('paths is required')
    start = _parse_when(payload.get('start') or '-8h')
    end = _parse_when(payload.get('end') or '')
    return_size = int(payload.get('returnSize') or 300)
    aggregation = payload.get('aggregation') or 'Average'
    try:
        ds = system.tag.queryTagHistory(paths=paths, startDate=start, endDate=end,
          returnSize=return_size, aggregationMode=aggregation, returnFormat='Wide')
        return _ds_to_table(ds)
    except Exception as e:
        return _err('query failed: %s' % str(e))

def handle_history_providers(payload):
    providers = []
    try:
        from com.inductiveautomation.ignition.gateway import IgnitionGateway
        context = IgnitionGateway.get()
        mgr = context.getHistoryManager()
        for p in mgr.getStores():
            providers.append(str(p))
    except Exception as e:
        return _err('could not enumerate history providers: %s' % str(e))
    return {'providers': providers}

def handle_alarms_status(payload):
    states = payload.get('states') or ['ActiveUnacked', 'ActiveAcked', 'ClearUnacked', 'ClearAcked']
    source = payload.get('source') or '*'
    display = payload.get('displayPath') or '*'
    limit = int(payload.get('limit') or 100)
    events = system.alarm.queryStatus(state=states, source=['*%s*' % source if source != '*' else '*'],
      displaypath=['*%s*' % display if display != '*' else '*'])
    collected = []
    for e in events:
        collected.append({
            'id': str(e.getId()),
            'name': str(e.getName()),
            'source': str(e.getSource()),
            'displayPath': str(e.getDisplayPath()),
            'priority': str(e.getPriority()),
            'state': str(e.getState())
        })
        if len(collected) >= limit:
            break
    return {'alarms': collected, 'truncated': len(events) > limit}

def handle_alarms_journal(payload):
    start = _parse_when(payload.get('start') or '-24h')
    end = _parse_when(payload.get('end') or '')
    states = payload.get('states') or None
    source = payload.get('source') or '*'
    limit = int(payload.get('limit') or 200)
    kwargs = {'startDate': start, 'endDate': end}
    if states:
        kwargs['state'] = states
    if source != '*':
        kwargs['source'] = ['*%s*' % source]
    events = system.alarm.queryJournal(**kwargs)
    collected = []
    for e in events:
        event_time = _fmt_date(e.getLastEventTime()) if hasattr(e, 'getLastEventTime') else None
        collected.append({
            'id': str(e.getId()),
            'name': str(e.getName()),
            'source': str(e.getSource()),
            'displayPath': str(e.getDisplayPath()),
            'priority': str(e.getPriority()),
            'state': str(e.getState()),
            'eventTime': event_time
        })
        if len(collected) >= limit:
            break
    return {'events': collected, 'truncated': len(events) > limit}

def handle_alarms_ack(payload):
    ids = payload.get('eventIds') or []
    if not ids:
        return _err('eventIds is required')
    notes = payload.get('notes') or None
    try:
        system.alarm.acknowledge(ids, notes)
        return {'acknowledged': len(ids)}
    except Exception as e:
        return _err('acknowledge failed: %s' % str(e))


def handle_db_named_query(payload):
    project = payload.get('project')
    path = payload.get('path')
    if not project or not path:
        return _err('project and path are required')
    params = payload.get('params') or {}
    try:
        result = system.db.runNamedQuery(project, path, params)
        if hasattr(result, 'getColumnCount'):
            return _ds_to_table(result)
        else:
            return {'value': _json_safe(result)}
    except Exception as e:
        return _err('named query failed: %s' % str(e))


def handle_db_query(payload):
    sql = payload.get('sql')
    if not sql:
        return _err('sql is required')
    database = payload.get('database') or ''
    args = payload.get('args') or []
    mutating = bool(payload.get('mutating'))
    try:
        if mutating:
            count = system.db.runPrepUpdate(sql, args, database)
            return {'rowsAffected': count}
        else:
            ds = system.db.runPrepQuery(sql, args, database)
            table = _ds_to_table(ds)
            if len(table['rows']) > 5000:
                table['rows'] = table['rows'][:5000]
                table['truncated'] = True
            return table
    except Exception as e:
        return _err('query failed: %s' % str(e))


def handle_files_list(payload):
    rel = payload.get('path') or ''
    recursive = bool(payload.get('recursive'))
    root = _safe_path(rel)
    if not os.path.isdir(root):
        return {'entries': []}
    entries = []
    if recursive:
        walker = os.walk(root)
    else:
        names = os.listdir(root)
        walker = [(root, [n for n in names if os.path.isdir(os.path.join(root, n))],
                   [n for n in names if not os.path.isdir(os.path.join(root, n))])]
    for dirpath, dirnames, filenames in walker:
        if '.resources' in dirnames:
            dirnames.remove('.resources')
        for name in dirnames + filenames:
            full_path = os.path.join(dirpath, name)
            is_dir = os.path.isdir(full_path)
            size = os.path.getsize(full_path) if not is_dir else 0
            entries.append({
                'path': full_path[len(PROJECTS_ROOT):].replace(os.sep, '/').lstrip('/'),
                'isDir': is_dir,
                'size': size
            })
    return {'entries': entries}


def handle_files_read(payload):
    rel = payload.get('path')
    if not rel:
        return _err('path is required')
    full = _safe_path(rel)
    if not os.path.isfile(full):
        return _err('file not found: %s' % rel)
    try:
        with codecs.open(full, 'r', 'utf-8') as f:
            content = f.read()
        return {'content': content}
    except Exception as e:
        return _err('read failed: %s' % str(e))


def handle_files_write(payload):
    rel = payload.get('path')
    content = payload.get('content')
    if not rel or content is None:
        return _err('path and content are required')
    full = _safe_path(rel)
    try:
        parent = os.path.dirname(full)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with codecs.open(full, 'w', 'utf-8') as f:
            f.write(content)
        return {'written': rel, 'bytes': len(content)}
    except Exception as e:
        return _err('write failed: %s' % str(e))


def handle_files_delete(payload):
    rel = payload.get('path')
    if not rel:
        return _err('path is required')
    recursive = bool(payload.get('recursive'))
    full = _safe_path(rel)
    try:
        if os.path.isfile(full):
            os.remove(full)
            return {'deleted': rel}
        elif os.path.isdir(full):
            if recursive:
                import shutil
                shutil.rmtree(full)
            else:
                os.rmdir(full)
            return {'deleted': rel}
        else:
            return _err('not found: %s' % rel)
    except Exception as e:
        return _err('delete failed: %s' % str(e))


def handle_trial_reset(payload):
    try:
        from com.inductiveautomation.ignition.gateway import IgnitionGateway
        context = IgnitionGateway.get()
        lm = context.getLicenseManager()
        if hasattr(lm, 'resetTrial'):
            lm.resetTrial()
        else:
            for method_name in dir(lm):
                if 'resetTrial' in method_name or 'trialReset' in method_name:
                    getattr(lm, method_name)()
                    break
            else:
                return _err('no trial reset method on LicenseManager', 'Reset the trial manually on the gateway homepage.')
        return {'reset': True}
    except Exception as e:
        return _err('trial reset failed: %s' % str(e), 'Reset the trial manually on the gateway homepage.')


# ------------------------------------------------------------------- dispatch

HANDLERS = {
    'ping': handle_ping,
    'tags/browse': handle_tags_browse,
    'tags/read': handle_tags_read,
    'tags/write': handle_tags_write,
    'tags/configure': handle_tags_configure,
    'history/query': handle_history_query,
    'history/providers': handle_history_providers,
    'alarms/status': handle_alarms_status,
    'alarms/journal': handle_alarms_journal,
    'alarms/ack': handle_alarms_ack,
    'db/named-query': handle_db_named_query,
    'db/query': handle_db_query,
    'files/list': handle_files_list,
    'files/read': handle_files_read,
    'files/write': handle_files_write,
    'files/delete': handle_files_delete,
    'trial/reset': handle_trial_reset,
}


def handle(request):
    endpoint = (request.get('remainingPath') or '').strip('/')
    handler = HANDLERS.get(endpoint)
    if handler is None:
        return {'json': {'ok': False, 'error': 'unknown endpoint: %s' % endpoint,
                         'remediation': 'Known endpoints: %s' % ', '.join(sorted(HANDLERS))}}

    payload, reject_response = _verify(request.get('data'))
    if reject_response is not None:
        return reject_response

    try:
        result = handler(payload)
    except ValueError as e:
        return {'json': {'ok': False, 'error': str(e)}}
    except Exception as e:
        LOGGER.warn('mcp-bridge %s failed: %s' % (endpoint, str(e)))
        return {'json': {'ok': False, 'error': str(e)}}

    if _is_err(result):
        return {'json': {'ok': False, 'error': result['error'],
                         'remediation': result.get('remediation', '')}}
    return {'json': {'ok': True, 'data': result}}
