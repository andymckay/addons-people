import hashlib
import json
import os

from datetime import datetime, timedelta
from functools import partial
from urllib import urlencode

from utils import get_weeks, log

import requests

bugzilla_rest = 'https://bugzilla.mozilla.org/rest/bug?'
bugzilla_query = 'https://bugzilla.mozilla.org/buglist.cgi?'


def bugs_assigned(person, **kw):
    kw = kw.copy()
    kw.update({
        'emailtype1': 'exact',
        'emailassigned_to1': '1',
        'email1': person['bugzilla_email'],
        'status': ['UNCONFIRMED', 'ASSIGNED', 'REOPENED', 'NEW']
    })
    return kw


def bugs_closed(person, **kw):
    kw = kw.copy()
    kw.update({
        'emailtype1': 'exact',
        'emailassigned_to1': '1',
        'email1': person['bugzilla_email'],
        'status': ['RESOLVED', 'VERIFIED', 'CLOSED']
    })
    return kw


def bugs_closed_component(component, **kw):
    kw = kw.copy()
    kw.update({
        'component': component,
        'status': ['RESOLVED', 'VERIFIED', 'CLOSED']
    })
    return kw


def reviews_assigned(person, **kw):
    kw = kw.copy()
    kw.update({
        'status': ['UNCONFIRMED', 'ASSIGNED', 'REOPENED', 'NEW'],
        'f1': 'flagtypes.name',
        'o1': 'substring',
        'v1': 'review?',
        'f2': 'requestees.login_name',
        'o2': 'substring',
        'v2': person['bugzilla_nick']
    })
    return kw


def ni_assigned(person, **kw):
    kw = kw.copy()
    kw.update({
        'status': ['UNCONFIRMED', 'ASSIGNED', 'REOPENED', 'NEW'],
        'f1': 'flagtypes.name',
        'o1': 'substring',
        'v1': 'needinfo?',
        'f2': 'requestees.login_name',
        'o2': 'substring',
        'v2': person['bugzilla_nick']
    })
    return kw


def reviews_involved(person, **kw):
    kw = kw.copy()
    kw.update({
        'f1': 'attachments.description',
        'o1': 'anywordssubstr',
        'v1': person['bugzilla_nick']
    })
    return kw


def as_query(person, query=None, **kw):
    query = globals().get(query)(person, **kw)
    new = {}
    translate = {'status': 'bug_status'}
    for k, v in query.items():
        new[translate.get(k, k)] = v

    return bugzilla_query + urlencode(new, True)


def rest_query(query, cache=True):
    query = bugzilla_rest + urlencode(query)

    if not cache:
        log.info('Note: not caching bugzilla query.')

    query_hash = hashlib.md5()
    query_hash.update(query)
    cache_key = 'bugzilla:' + query_hash.hexdigest()
    filename = os.path.join('cache', cache_key + '.json')

    if cache and os.path.exists(filename):
        return json.load(open(filename, 'r'))

    log.info('Bugzilla: {}'.format(query))
    result = requests.get(query).json()
    if cache:
        json.dump(result, open(filename, 'w'))

    return result


def get_query_per_week(person, query, parse=None, start=None, end=None):
    assert parse
    weeks = get_weeks(start, end)
    results = []
    for k, (start, end) in enumerate(weeks):
        query_url = query(person, **parse(start, end))
        # Don't cache the last two weeks.
        cache = bool(os.getenv('FORCE_CACHE', k < (len(weeks) - 2)))
        result = rest_query(query_url, cache=cache)
        results.append((start, end, len(result['bugs'])))

    return results


def parse(week_start, week_end):
    return {
        'chfieldto': week_end.strftime('%Y-%m-%d'),
        'chfield': 'cf_last_resolved',
        'chfieldfrom': week_start.strftime('%Y-%m-%d'),
    }


def bugs_closed_per_week(person, start=None, end=None):
    return reversed(
        get_query_per_week(person, bugs_closed, parse=parse, start=start, end=end)
    )


def reviews_involved_per_week(person, start=None, end=None):
    return reversed(
        get_query_per_week(person, reviews_involved, parse=parse, start=start, end=end)
    )


def bugs_closed_by_component_per_week(product, component, start=None, end=None):
    return reversed(
        get_query_per_week(component, bugs_closed_component, parse=parse, start=start, end=end)
    )


queries = {
    'bugs_assigned': partial(as_query, query='bugs_assigned'),
    'closed': partial(as_query, query='bugs_closed'),
    'reviews_assigned': partial(as_query, query='reviews_assigned'),
    'ni_assigned': partial(as_query, query='ni_assigned')
}
