import os
import requests
import time

from utils import log

BASE_URL = 'https://bugzilla.mozilla.org'
URL = '{}/rest/bug'.format(BASE_URL)

BUG_CACHE = {}


def get_overall_blockers(data):
    start = time.time()
    components = [v[1] for v in data['bugzilla']['components']]
    params = {
        'f1': 'blocked',
        'o1': 'isnotempty',
        'include_fields': 'blocks,id,summary',
        'status': ['UNCONFIRMED', 'NEW', 'ASSIGNED', 'REOPENED'],
        'component': components
    }
    res = requests.get(URL, params=params)
    res.raise_for_status()
    log.debug('Getting overall blockers took: {}'.format(time.time() - start))
    return res.json()['bugs']


def get_one_bug(id):
    if id in BUG_CACHE:
        return BUG_CACHE[id]

    url = URL + '/%s' % id
    params = {
        'include_fields': 'id,status,resolution,blocks'
    }

    res = requests.get(url, params=params)
    if res.status_code in (400, 401):
        log.warning(
            'Failed to get bug {} response {}'.format(id, res.status_code))
        return None

    res.raise_for_status()
    BUG_CACHE[id] = res.json()['bugs'][0]
    return BUG_CACHE[id]


def recurse_blockers(bug):
    recurse = {}
    log.debug('Recursing down for bug: {}'.format(bug['id']))

    def lookup_bugs(lookup):
        for bug in lookup['blocks']:
            blocker = get_one_bug(bug)
            if blocker:
                recurse[blocker['id']] = blocker
                lookup_bugs(blocker)

    lookup_bugs(bug)
    return recurse


def collect(data):
    if not data['bugzilla']['components']:
        return []

    blocks = {}
    for bug in get_overall_blockers(data):
        if len(bug['blocks']) > 2:
            bugs = recurse_blockers(bug)
            data = {
                'open': [],
                'closed': [],
                'total': 0,
                'id': bug['id'],
                'summary': bug['summary']
            }
            for blockers_bug_id, blockers_bug in bugs.items():
                if blockers_bug['status'] in ['RESOLVED']:
                    data['closed'].append(blockers_bug)
                else:
                    data['open'].append(blockers_bug)
                data['total'] += 1

            blocks[bug['id']] = data

    bugs = sorted([(v['total'], v) for k, v in blocks.items()])
    return list(reversed([v for _, v in bugs]))
