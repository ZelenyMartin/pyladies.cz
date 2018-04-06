#!/usr/bin/env python3

"""Create or serve the pyladies.cz website
"""

import sys
if sys.version_info < (3, 0):
    raise RuntimeError('You need Python 3.')

import os
import fnmatch
import datetime
import collections

from flask import Flask, render_template, url_for, send_from_directory
from flask_frozen import Freezer
import yaml
import jinja2
import markdown

from elsa import cli

app = Flask('pyladies_cz')
app.config['TEMPLATES_AUTO_RELOAD'] = True

orig_path = os.path.join(app.root_path, 'original/')
v1_path = os.path.join(orig_path, 'v1/')


def redirect(url):
    """Return a response with a Meta redirect"""

    # With static pages, we can't use HTTP redirects.
    # Return a page wit <meta refresh> instead.
    #
    # When Frozen-Flask gets support for redirects
    # (https://github.com/Frozen-Flask/Frozen-Flask/issues/81),
    # this should be revisited.

    return render_template('meta_redirect.html', url=url)


########
## Views

@app.route('/')
def index():
    current_meetups = collections.OrderedDict(
        (city, read_meetups_yaml('meetups/{}.yml'.format(city)))
        for city in ('praha', 'brno', 'ostrava'))
    news = read_news_yaml('news.yml')
    return render_template('index.html',
                           current_meetups=current_meetups,
                           news=news)

@app.route('/praha/')
def praha():
    return render_template('city.html',
                           city_slug='praha',
                           city_title='Praha',
                           team_name='Tým pražských PyLadies',
                           meetups=read_meetups_yaml('meetups/praha.yml'),
                           team=read_yaml('teams/praha.yml'))

@app.route('/brno/')
def brno():
    return render_template('city.html',
                           city_slug='brno',
                           city_title='Brno',
                           team_name='Tým brněnských PyLadies',
                           meetups=read_meetups_yaml('meetups/brno.yml'),
                           team=read_yaml('teams/brno.yml'))

@app.route('/ostrava/')
def ostrava():
    return render_template('city.html',
                           city_slug='ostrava',
                           city_title='OSTRAVA!!!',
                           team_name='Tým ostravských PyLadies',
                           meetups=read_meetups_yaml('meetups/ostrava.yml'),
                           team=read_yaml('teams/ostrava.yml'))

@app.route('/<city>_course/')
def course_redirect(city):
    return redirect(url_for(city, _anchor='meetups'))

@app.route('/<city>_info/')
def info_redirect(city):
    return redirect(url_for(city, _anchor='city-info'))

@app.route('/praha-cznic/')
def praha_cznic():
    '''
    Pražský kurz v CZ.NIC
    '''
    return render_template('praha.html', location='cznic', plan=read_lessons_yaml('plans/praha-cznic.yml'))

@app.route('/praha-ntk/')
def praha_ntk():
    '''
    Pražský kurz v NTK
    '''
    return render_template('praha.html', location='ntk', plan=read_lessons_yaml('plans/praha-ntk.yml'))

@app.route('/stan_se/')
def stan_se():
    return render_template('stan_se.html')

@app.route('/faq/')
def faq():
    return render_template('faq.html')

@app.route('/v1/<path:path>')
def v1(path):
    if path in REDIRECTS:
        return redirect(REDIRECTS[path])
    return send_from_directory(v1_path, path)

@app.route('/index.html')
def index_html():
    return redirect(url_for('index'))

@app.route('/course.html')
def course_html():
    return send_from_directory(orig_path, 'course.html')

@app.route('/googlecc704f0f191eda8f.html')
def google_verification():
    # Verification page for GMail on our domain
    return send_from_directory(app.root_path, 'google-verification.html')


##########
## Helpers

md = markdown.Markdown(extensions=['meta', 'markdown.extensions.toc'])

@app.template_filter('markdown')
def convert_markdown(text, inline=False):
    result = jinja2.Markup(md.convert(text))
    if inline and result[:3] == '<p>' and result[-4:] == '</p>':
        result = result[3:-4]
    return result

@app.template_filter('date_range')
def date_range(dates, sep='–'):
    start, end = dates
    pieces = []
    if start != end:
        if start.year != end.year:
            pieces.append('{d.day}. {d.month}. {d.year}'.format(d=start))
        elif start.month != end.month:
            pieces.append('{d.day}. {d.month}.'.format(d=start))
        else:
            pieces.append('{d.day}.'.format(d=start))
        pieces.append('–')
    pieces.append('{d.day}. {d.month}. {d.year}'.format(d=end))

    return ' '.join(pieces)


def read_yaml(filename):
    with open(filename, encoding='utf-8') as file:
        data = yaml.safe_load(file)
    return data

def read_lessons_yaml(filename):
    data = read_yaml(filename)

    # workaround for http://stackoverflow.com/q/36157569/99057
    # Convert datetime objects to strings
    for lesson in data:
        if 'date' in lesson:
            lesson['dates'] = [lesson['date']]
        if 'description' in lesson:
            lesson['description'] = convert_markdown(lesson['description'],
                                                     inline=True)
        for mat in lesson.get('materials', ()):
            mat['name'] = convert_markdown(mat['name'], inline=True)

        # If lesson has no `done` key, add them according to lesson dates
        # All lesson's dates must be in past to mark it as done
        done = lesson.get('done', None)
        if done is None and 'dates' in lesson:
            all_done = []
            for date in lesson['dates']:
                all_done.append(datetime.date.today() > date)
            lesson['done'] = all(all_done)

    return data


def read_meetups_yaml(filename):
    data = read_yaml(filename)

    today = datetime.date.today()

    previous = None

    for meetup in data:

        # 'date' means both start and end
        if 'date' in meetup:
            meetup['start'] = meetup['date']
            meetup['end'] = meetup['date']

        # Derive a URL for places that don't have one from the location
        if 'place' in meetup:
            if ('url' not in meetup['place']
                    and {'latitude', 'longitude'} <= meetup['place'].keys()):
                meetup['place']['url'] = (
                    'http://mapy.cz/zakladni?q={p[name]},'
                    '{p[latitude]}N+{p[longitude]}E'.format(p=meetup['place']))

        # Figure out the status of registration
        if 'registration' in meetup:
            if 'end' in meetup['registration']:
                if meetup['start'] <= today:
                    meetup['registration_status'] = 'meetup_started'
                elif meetup['registration']['end'] >= today:
                    meetup['registration_status'] = 'running'
                else:
                    meetup['registration_status'] = 'closed'
            else:
                meetup['registration_status'] = 'running'

        meetup['current'] = ('end' not in meetup) or (meetup['end'] >= today)

        # meetup['parallel_runs'] will contain a shared list of all parallel runs
        if meetup.get('parallel-with-previous'):
            meetup['parallel_runs'] = previous['parallel_runs']
        else:
            meetup['parallel_runs'] = []
        meetup['parallel_runs'].append(meetup)
        previous = meetup

    return list(reversed(data))

def read_news_yaml(filename):
    data = read_yaml(filename)
    today = datetime.date.today()
    news = []

    for new in data:
        if new['expires'] >= today:
            news.append(new)

    return news

def pathto(name, static=False):
    if static:
        prefix = '_static/'
        if name.startswith(prefix):
            return url_for('static', filename=name[len(prefix):])
        prefix = 'v1/'
        if name.startswith(prefix):
            return url_for('v1', path=name[len(prefix):])
        return name
    return url_for(name)


@app.context_processor
def inject_context():
    return {
        'pathto': pathto,
        'today': datetime.date.today(),
    }


############
## Redirects

REDIRECTS_DATA = read_yaml('redirects.yml')

REDIRECTS = {}
for directory, pages in REDIRECTS_DATA['naucse-lessons'].items():
    for html_filename, lesson in pages.items():
        new_url = 'http://naucse.python.cz/lessons/{}/'.format(lesson)
        REDIRECTS['{}/{}'.format(directory, html_filename)] = new_url


##########
## Freezer

freezer = Freezer(app)

@freezer.register_generator
def v1():
    IGNORE = ['*.aux', '*.out', '*.log', '*.scss', '.travis.yml', '.gitignore']
    for name, dirs, files in os.walk(v1_path):
        if '.git' in dirs:
            dirs.remove('.git')
        for file in files:
            if file == '.git':
                continue
            if not any(fnmatch.fnmatch(file, ig) for ig in IGNORE):
                path = os.path.relpath(os.path.join(name, file), v1_path)
                yield {'path': path}
    for path in REDIRECTS:
        yield url_for('v1', path=path)

OLD_CITIES = 'praha', 'brno', 'ostrava'

@freezer.register_generator
def course_redirect():
    for city in OLD_CITIES:
        yield {'city': city}

@freezer.register_generator
def info_redirect():
    for city in OLD_CITIES:
        yield {'city': city}

if __name__ == '__main__':
    cli(app, freezer=freezer, base_url='http://pyladies.cz')
