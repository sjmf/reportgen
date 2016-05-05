#!/usr/bin/env python3
# coding: utf-8
import io, os, errno, re, json, tempfile, logging, threading, sys
from flask import Flask, Blueprint, current_app, escape, redirect, render_template, request, Response, send_from_directory, session, url_for
from flask.ext.session import Session
from werkzeug import secure_filename
from time import sleep
from redis import Redis
import report

# Set up logger
log = logging.getLogger(__name__)

# Create flask app
app = Flask(__name__)

# Set up blueprint
prefix = os.environ.get('PROXY_PATH', '')
bax = Blueprint('bax', __name__, template_folder='templates')
# Look at end of file for where this blueprint is actually registered to the app

# App options (loaded from_object)
UPLOAD_FOLDER = '/tmp/uploads'
MAX_CONTENT_LENGTH = 512 * 1024 * 1024
DEBUG = True

ALLOWED_EXTENSIONS = set(['txt', 'csv', 'bin', 'bax'])
IMAGE_EXTENSIONS = set(['jpg', 'png', 'svg', 'gif'])

host = os.environ.get('REDIS_URL', '://' + os.environ.get('REDIS_HOSTNAME', 'localhost'))
redis = Redis(host=(host.split(':')[1][2:]))

# Flask-Session module setup
SESSION_TYPE = 'redis'
SESSION_REDIS = redis 
app.config.from_object(__name__)
Session(app)

flask_options = {
    'host':'0.0.0.0',
    'threaded':True
}


'''
   Auxilliary functions 
'''
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path): pass
        else: raise


def escape_filename(filename):
    return re.sub('[^a-zA-Z0-9\-_\.]', '', secure_filename(filename))


def save_file(fil, extensions_list):
    original_name = escape_filename(fil.filename)
    file_extension = original_name.rsplit('.', 1)[1].lower() if '.' in original_name else ''
    temporary_name = next(tempfile._get_candidate_names()) +'.'+ file_extension

    if fil and file_extension in extensions_list:
        # Check the folder exists
        mkdir_p(app.config['UPLOAD_FOLDER'])
        # Put it on the disk:
        path = os.path.join(app.config['UPLOAD_FOLDER'], temporary_name)
        fil.save(path)
        file_size = os.stat(path).st_size
        
        return {
            'original_name'   : original_name,
            'temporary_name'  : temporary_name,
            'file_extension'  : file_extension,
            'file_size'       : file_size,
            'content_type'    : fil.content_type,
        }

    return None


# Report generation worker thread
def report_worker(sid):
    try:
        job = get_job(sid) 

        log.info("=============  STARTING WORKER  ==============")
        
        # Expand paths to full location on filesystem 
        output_filename = os.path.join(
            app.config['UPLOAD_FOLDER'], 
            next(tempfile._get_candidate_names()) + '.pdf')
        
        # Make list of input datafiles
        input_datafiles = [
                os.path.join( app.config['UPLOAD_FOLDER'], f['temporary_name'])
            for f in get_files(sid) ]

        report.report(input_datafiles, output_filename, 
                    **{**job, 'pdf':True, 'htm':False})

        log.info("=============  WORKER FINISHED  ==============")

        # Update finished job 
        upd_job(sid, 'generated_pdf', output_filename)
        upd_job(sid, 'status', 'done')

    except Exception as e:
        log.error("Exception occurred in worker thread")
        log.error(sys.exc_info()[0])

        upd_job(sid, 'status', 'error')
        upd_job(sid, 'generated_pdf', None)
        raise e


# Store files in redis by keys prefix:sid:filename 
def rkey(prefix, sid, suffix=None):
    return prefix + ":" + sid + (":" + suffix if suffix else '')

def dict_utf8(j):
    return { k.decode('utf-8') : v.decode('utf-8') for k,v in j.items() } 

def get_template_variables():
    tpl = dict(session)
    job = get_job(session.sid)
    fil = get_files(session.sid)

    if job:
        tpl['job'] = job
    if fil:
        tpl['files'] = fil
    
    return tpl

''' 
    File handling
'''
def list_fkeys(sid='*'):
    fkeys = []
    cursor = 0

    while True:
        cursor, keys = redis.scan(cursor, match=rkey('files', sid, '*'))
        fkeys.extend(keys)
        #log.debug("Redis cursor @{0}, got {1} keys".format(cursor, len(keys)))
        if cursor == 0:
            return fkeys


def get_files(sid):
    return sorted( [
            dict_utf8(j)     
                for j in [ redis.hgetall(key) for key in list_fkeys(sid) ]
        ], 
        key=lambda x: x['original_name'])


def add_file(file_info):
    key = rkey('files', session.sid, file_info['original_name'])
    log.debug(key)
    if not redis.exists(key):
        redis.hmset(key, file_info)
    else:
        raise KeyError("File already exists!")


def count_files():
    return len(list_fkeys())


# Atomic multikey delete: http://stackoverflow.com/a/16974060/1681205
def delete_files():
    return redis.eval("return redis.call('del', unpack(redis.call('keys', ARGV[1])))", 0, rkey('files', session.sid, '*'))

'''
    Job handling
'''
def get_job(sid):
    return dict_utf8(redis.hgetall( rkey('job',sid) ))

def put_job(sid,job):
    return redis.hmset(rkey('job', sid), job)

def upd_job(sid, key, value):
    return redis.hset( rkey('job', sid), key, value)

def has_job(sid):
    return redis.exists( rkey('job', sid) )

def rem_job(sid):
    return redis.delete( rkey('job', sid) )


'''
    Application Routes
'''
@bax.route('/', methods=['GET'])
def index():
    log.debug(session.sid)
    if has_job(session.sid):
        return redirect('/job')
    return render_template("upload.htm")


@bax.route('/generate', methods=['POST'])
def generate():
    if not has_job(session.sid):
        try:
            job = {
                'location'     : escape(request.form['location']),
                'description'  : escape(request.form['description']),
                'status'       : 'running',
            }
            put_job(session.sid, job)    # Put job quickly to avoid races

            if request.files:
                fil = next(iter(request.files.values()))
                file_info = save_file(fil, IMAGE_EXTENSIONS)
                job.update({
                    'map_filename' : os.path.join(app.config['UPLOAD_FOLDER'], escape_filename(file_info['temporary_name'])),
                    'map_file'     : escape_filename(file_info['original_name']),
                })

        except Exception as e:
            if job:
                job['status'] = 'error'
                put_job(session.sid, job)
            raise e
        else:
            put_job(session.sid, job)
            thread = threading.Thread(target=report_worker, args=(session.sid,))
            thread.start()

    return redirect('/job')


@bax.route('/job', methods=['GET', 'POST'])
def job():
    return render_template("jobstatus.htm", **get_template_variables() )


@bax.route('/download', methods=['GET'])
def download():
    job = get_job(session.sid)
    if 'generated_pdf' in job:
        return send_from_directory(
            app.config['UPLOAD_FOLDER'], 
            job['generated_pdf'].split('/')[-1],
            as_attachment=True,
            attachment_filename=escape_filename(
                (job['location'] if job['location'] else 'output')
                    +'.pdf'),
            mimetype='application/pdf')

    return "No file", 400


'''
    API Routes
'''
@bax.route("/clear", methods=['GET', 'POST'])
def clear():
    for fil in get_files(session.sid):
        try:
            os.remove(fil['temporary_name']) 
        except FileNotFoundError:
            pass
    delete_files()
    return 'Files cleared', 200


@bax.route("/upload", methods=['PUT'])
def upload():
    fil = request.files['file']
    file_info = save_file(fil, ALLOWED_EXTENSIONS)
    try:
        if file_info:
            add_file(file_info)
            log.debug("{} files uploaded".format(count_files()))

            return "File Received: {}".format(file_info['original_name']), 200
    except KeyError as e:
        return "File '{}' already uploaded!".format(file_info['original_name']), 400
    return "File type '{}' rejected".format(file_info['file_extension']), 400


@bax.route('/status', methods=['GET'])
def status():
    return Response(json.dumps( get_template_variables() ), mimetype='application/json')


@bax.route('/cancel', methods=['GET', 'POST'])
def cancel():
    if has_job(session.sid):
        ### Remove files
        job = get_job(session.sid)
        try:
            if 'map_file' in job:
                os.unlink(job['map_filename'])
            if 'generated_pdf' in job:
                os.unlink(job['generated_pdf'])
        except:
            log.warning("Exception in cancel")
            pass
        finally:
            rem_job(session.sid)

        if request.args.get('redirect'):
            return redirect('/')
        return Response(json.dumps({ 'cancel':'ok' }), 200 
                , mimetype='application/json')
    return Response(json.dumps({ 'cancel':'no-job' }), 200 
            , mimetype='application/json')


'''
    Register blueprint to the app
'''
app.register_blueprint(bax, url_prefix=prefix)

# Main. Does not run when running with WSGI
if __name__ == "__main__":
    strh = logging.StreamHandler() 
    strh.setLevel(logging.DEBUG)
    log.addHandler(strh)
    log.setLevel(logging.DEBUG) 

    for l in ['report.py','datahandling.py']:
        l = logging.getLogger(l)
        l.propagate = True
        l.setLevel(logging.DEBUG)

    app.run(**flask_options)

