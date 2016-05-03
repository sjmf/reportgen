#!/usr/bin/env python3
# coding: utf-8
import io, os, errno, re, json, tempfile, logging, threading, sys
import report
from flask import Flask, current_app, escape, redirect, render_template, request, Response, send_from_directory, session, url_for
from flask.ext.session import Session
from werkzeug import secure_filename
from time import sleep
from redis import Redis
import pickle
import pprint

# Set up logger
log = logging.getLogger(__name__)

# Create flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024
app.config['DEBUG'] = True

ALLOWED_EXTENSIONS = set(['txt', 'csv', 'bin', 'bax'])
IMAGE_EXTENSIONS = set(['jpg', 'png', 'svg', 'gif'])
SESSION_TYPE = 'redis'

app.config.from_object(__name__)
Session(app)

redis = Redis()

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


# Override get_session directly from Redis (for thread use)
def get_session(sid):
    return pickle.loads(redis.get("session:"+sid))


def put_session(session, sid):
    redis.set("session:"+sid, pickle.dumps(session)) 


# Start worker thread job
def start_job():   
    # Must write session back first! There is a race condition between
    # the session being written on route return and the thread starting!
    put_session(session, session.sid)
    thread = threading.Thread(target=report_worker, args=(session.sid,))
    thread.start()


# Report generation worker thread
def report_worker(sid):
    try:
        session = get_session(sid)
        job = session['job']

        log.info("=============  STARTING WORKER  ==============")
#        log.debug("Here's my session:")
#        log.debug(pprint.pformat(session))
        
        # Expand paths to full location on filesystem 
        output_filename = os.path.join(
            app.config['UPLOAD_FOLDER'], 
            next(tempfile._get_candidate_names()) + '.pdf')
        
        # Make list of input datafiles
        input_datafiles = [
                os.path.join( app.config['UPLOAD_FOLDER'], f['temporary_name'])
            for f in get_files() ]

        report.report(input_datafiles, output_filename, 
                    **{**job, 'pdf':True, 'htm':False})

        log.info("=============  WORKER FINISHED  ==============")

        # Put generated pdf in the session last thing before finally

        # Update session
        session = get_session(sid)
        session['generated_pdf'] = output_filename
        session['status'] = 'done'

    except Exception as e:
        log.error("Exception occurred in worker thread")
        log.error(sys.exc_info()[0])

        session['status'] = 'error'
        session['generated_pdf'] = None
        raise

    finally:
        put_session(session, sid)


'''
    Application Routes
'''
@app.route('/', methods=['GET'])
def index():
    # Set up some session variables so they are not undefined
    if 'status' not in session:
        session['status'] = 'ready'

    if 'job' in session.keys():
        return redirect('/job')
    return render_template("upload.htm")


@app.route('/generate', methods=['POST'])
def generate_report():
    if 'job' not in session:
        session['job'] = {
            'location'     : escape(request.form['location']),
            'description'  : escape(request.form['description']),
            'sid'          : session.sid,
        }

        if request.files:
            fil = next(iter(request.files.values()))
            file_info = save_file(fil, IMAGE_EXTENSIONS)
            session['job'].update({
                'map_filename' : os.path.join(app.config['UPLOAD_FOLDER'], escape_filename(file_info['temporary_name'])),
                'map_file'     : escape_filename(file_info['original_name']),
            })

        start_job()
        session['status'] = 'running'
    return redirect('/job')


@app.route('/job', methods=['GET', 'POST'])
def jobs_page():
    return render_template("jobstatus.htm", **dict(session)) 


@app.route('/download', methods=['GET'])
def get_file():
    if 'generated_pdf' in session:
        return send_from_directory(
            app.config['UPLOAD_FOLDER'], 
            session['generated_pdf'].split('/')[-1],
            as_attachment=True,
            attachment_filename=escape_filename(
                (session['job']['location'] if session['job']['location'] else 'output')
                    +'.pdf'),
            mimetype='application/pdf')

    return "No file", 400


# Store files in redis by keys files:sid:filename 
def fkey(sid, filename):
    return "files:"+sid+":"+filename


def list_fkeys(sid=None):
    fkeys = []
    cursor = 0
    while True:
        cursor, keys = redis.scan(cursor, match=fkey(session.sid, '*'))
        fkeys.extend(keys)
        log.debug("Redis cursor @{0}, got {1} keys".format(cursor, len(keys)))
        if cursor == 0:
            return fkeys


def get_files():
    return sorted( [
            { k.decode('utf-8') : v.decode('utf-8') for k,v in j.items() } 
                for j in [ redis.hgetall(key) for key in list_fkeys() ]
        ], 
        key=lambda x: x['original_name'])


def add_file(file_info):
    key = fkey(session.sid, file_info['original_name'])
    log.debug(key)
    if not redis.exists(key):
        redis.hmset(key, file_info)
    else:
        raise KeyError("File already exists!")


def count_files():
    return len(list_fkeys())


# Atomic multikey delete: http://stackoverflow.com/a/16974060/1681205
def delete_files():
    return redis.eval("return redis.call('del', unpack(redis.call('keys', ARGV[1])))", 0, fkey(session.sid, '*'))


@app.route("/clear", methods=['GET', 'POST'])
def clear_files():
    for fil in get_files():
        try:
            os.remove(fil['temporary_name']) 
        except FileNotFoundError:
            pass
    delete_files()
    return 'Files cleared', 200


@app.route("/upload", methods=['PUT'])
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


@app.route('/status', methods=['GET'])
def job_status():
    return Response(json.dumps({
            **dict(session),
            'files' : get_files()
        }), mimetype='application/json')


@app.route('/cancel', methods=['GET', 'POST'])
def job_cancel():
    if 'job' in session:
        ### Remove files
        try:
            if 'map_file' in session:
                os.unlink(session['job']['map_filename'])
            if 'generated_pdf' in session:
                os.unlink(session['generated_pdf'])
        except:
            log.warning("Exception in cancel")
            pass
        finally:
            if 'generated_pdf' in session:
                del session['generated_pdf']
            del session['job']
        
        if request.args.get('redirect'):
            return redirect('/')
        return Response(json.dumps({ 'cancel':'ok' }), 200 
                , mimetype='application/json')
    return Response(json.dumps({ 'cancel':'no-job' }), 200 
            , mimetype='application/json')


if __name__ == "__main__":
    strh = logging.StreamHandler() 
    strh.setLevel(logging.DEBUG)
    log.addHandler(strh)
    log.setLevel(logging.DEBUG) 

    for l in ['report.py','datahandling.py']:
        l = logging.getLogger(l)
        l.propagate = True
        l.setLevel(logging.DEBUG)

    mkdir_p(app.config['UPLOAD_FOLDER'])
    app.run(**flask_options)

