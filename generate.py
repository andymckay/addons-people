import csv
from datetime import datetime
import json
import StringIO

import os
import sys
import shutil

from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))

import blockers
import bugzilla
import github

from utils import Encoder, log


def clean():
    for filename in os.listdir('build'):
        if filename.startswith('.keep'):
            continue
        os.remove(os.path.join('build', filename))

    for filename in os.listdir('static'):
        shutil.copyfile(
            os.path.join('static', filename),
            os.path.join('build', filename)
        )


def load_data(filename):
    data = json.load(open(filename, 'r'))

    data['start'] = datetime.strptime(
        data.get('start_date', '2016-01-01'),
        '%Y-%m-%d'
        ).date()
    data['end'] = datetime.strptime(
        data.get('end_date', datetime.today().strftime('%Y-%m-%d')),
        '%Y-%m-%d'
        ).date()
    return data


def copy_into_build(filename, output):
    open(os.path.join('build', filename), 'w').write(output)


def merge(method, person, start=None, end=None):
    # Assume everyone has a bugzilla account.
    bugzilla_dates = getattr(bugzilla, method)(person, start=start, end=end)

    github_dates = {}
    if person['github']:
        # Annotate in the github data.
        github_dates = getattr(github, method)(person, start=start, end=end)
        github_dates = dict([(start, num) for start, _, num in github_dates])

    merged = []
    maximum = 0
    for entries in bugzilla_dates:
        total = github_dates.get(entries[0], 0) + entries[2]
        maximum = max(maximum, total)
        merged.append({
            'start': entries[0],
            'end': entries[1],
            'bugzilla': entries[2],
            'github': github_dates.get(entries[0], 0),
            'total': total
        })

    return {'merged': merged, 'max': maximum}


def merge_component(method, product, component, start=None, end=None):
    bugzilla_dates = getattr(bugzilla, method)(product, component, start=start, end=end)

    merged = []
    maximum = 0
    for entries in bugzilla_dates:
        maximum = max(maximum, entries[2])
        merged.append({
            'start': entries[0],
            'end': entries[1],
            'bugzilla': entries[2],
            'total': entries[2]
        })

    return {'merged': merged, 'max': maximum}


def csv_file(data):
    output = StringIO.StringIO()
    writer = csv.DictWriter(output, data['merged'][0].keys())
    writer.writeheader()
    for row in data['merged']:
        writer.writerow(row)

    output.seek(0)
    return output.getvalue()


def generate_components(filename, template, data):
    for product, full, shorter in data['bugzilla']['components']:
        new_filename = 'component-{}.html'.format(shorter)
        result = merge_component(
            'bugs_closed_by_component_per_week',
            product, 
            full,
            start=data['start'],
            end=data['end']
        )
        copy_into_build(
            new_filename,
            template.render(
                data=data,
                component=full,
                shorter=shorter,
                bits={'bugs_closed_by_component_per_week': result}
            )
        )
        new_filename = 'component-{}.csv'.format(shorter)
        copy_into_build(
            new_filename,
            csv_file(result)
        )

def generate_index(filename, template, data):
    people = sorted((k, v) for k, v in data['people'].items())
    components = data.get('bugzilla', {}).get('components', [])
    copy_into_build(
        filename,
        template.render(
            data=data, people=people,
            bugzilla_components=components,
            bugzilla_queries=bugzilla.queries
        )
    )


def generate_blockers(filename, template, data):
    bugs = blockers.collect(data)
    copy_into_build(
        filename,
        template.render(
            data=data, blockers=bugs
        )
    )
    copy_into_build(
        filename.replace('.html', '.json'),
        json.dumps(bugs, cls=Encoder, indent=2)
    )


def generate_templates(data):
    data['generated'] = datetime.now()
    for filename in os.listdir('templates'):
        if filename == 'layout.html':
            continue

        name = os.path.splitext(filename)[0]
        method = globals().get('generate_' + name)
        if not method:
            print ('No method: generate_{} found for file: {}'
                   .format(name, filename))
        else:
            method(filename, env.get_template(filename), data)


if __name__=='__main__':
    clean()
    assert len(sys.argv) == 2, "Specify a JSON config file."
    data = load_data(sys.argv[1])
    generate_templates(data)
