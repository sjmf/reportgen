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
logging.getLogger().setLevel(logging.DEBUG)
log = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024
app.config['DEBUG'] = True

ALLOWED_EXTENSIONS = set(['txt', 'csv', 'bin', 'bax'])
IMAGE_EXTENSIONS = set(['jpg', 'png', 'svg', 'gif'])
SESSION_TYPE = 'redis'

app.config.from_object(__name__)
Session(app)

flask_options = {
    'host':'0.0.0.0',
    'threaded':True
}

# Store for stream loggers
output_loggers = {}

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

def get_session(sid):
    redis = Redis()
    return pickle.loads(redis.get("session:"+sid))

def put_session(session, sid):
    redis = Redis()
    redis.set("session:"+sid, pickle.dumps(session)) 

'''
    Application Routes
'''
@app.route('/', methods=['GET'])
def index():
    # Set up some session variables so they are not undefined
    if 'status' not in session:
        session['status'] = 'ready'

    if 'files' not in session:
        session['files'] = []

    if 'job' in session.keys():
        return redirect('/job')
    return render_template("upload.htm")


@app.route("/clear", methods=['GET', 'POST'])
def clear_files():
    for fil in session['files']:
        try:
            os.remove(fil['temporary_name']) 
        except FileNotFoundError:
            pass
    session['files'] = []
    return 'Files cleared', 200


@app.route('/files/<path:path>', methods=['DELETE'])
def delete_file(path):
    os.remove(escape_filename(path))
    return 'File deleted', 200


@app.route("/upload", methods=['PUT'])
def upload():
    # WARNING: session['files'].append() is NOT threadsafe.
    # concurrent file uploads are broken until I rewrite Session
    # handling to not use https://github.com/fengsp/flask-session.

    fil = request.files['file']

    file_info = save_file(fil, ALLOWED_EXTENSIONS)
    if file_info:
        session['files'].append(file_info)
        log.debug("{} files uploaded".format(len(session['files'])))

        return "File Received: {}".format(file_info['original_name']), 200
    return "File type '{}' is not allowed.".format(file_info['file_extension']), 401


# Start worker thread job and capture its output
def start_job():
    ### Create the loggers
    modules = ['reporting.py','datahandling.py', __name__]#'graphing.py',
    sublogs = [ logging.getLogger(l) for l in modules ]
    [ sublog.setLevel(logging.DEBUG) for sublog in sublogs ]

    ### Handle output with a StringIO object
    stream = io.StringIO()
    output_loggers[session.sid] = stream

    [[ sublog.removeHandler(handler) for handler in sublog.handlers ] for sublog in sublogs ]
    ch = logging.StreamHandler(stream)
    ch.setLevel(logging.DEBUG)

    ### Add a formatter:
    fmt = logging.Formatter('%(relativeCreated)6d %(threadName)s %(message)s')
    #fmt = logging.Formatter('%(message)s')
    ch.setFormatter(fmt)

    ### Add the handler to the loggers
    [ sublog.addHandler(ch) for sublog in sublogs ]

    ### Add another handler for terminal output
    strh = logging.StreamHandler() 
    strh.setLevel(logging.DEBUG)
    [ sublog.addHandler(strh) for sublog in sublogs ]

    log.info("===============  JOB SETUP  ==================")
    thread = threading.Thread(target=report_worker, args=(session.sid,))
    thread.start()

# Report generation worker thread
def report_worker(sid):
    try:
        session = get_session(sid)
        job = session['job']

        log.info("=============  STARTING WORKER  ==============")
        log.debug("Here's my session:")
        log.debug(pprint.pformat(session))

        
        # Expand paths to full location on filesystem 
        output_filename = os.path.join(
            app.config['UPLOAD_FOLDER'], 
            next(tempfile._get_candidate_names()) + '.pdf')
        
        # Make list of input datafiles
        input_datafiles = [
                os.path.join( app.config['UPLOAD_FOLDER'], f['temporary_name'])
            for f in session['files'] ]

        report.report(input_datafiles, output_filename, 
                    **{**job, 'pdf':True, 'htm':False})
        
        log.info("=============  WORKER FINISHED  ==============")
        
        # Put generated pdf in the session last thing before finally

        # Update session
        session = get_session(sid)
        session['generated_pdf'] = output_filename
        session['status'] = 'done'

    except Exception as e:
        log.critical("Exception occurred in worker thread")
        log.critical(sys.exc_info()[0])

        session['status'] = 'error'
        session['generated_pdf'] = None
        raise

    finally:
        put_session(session, sid)

        # Close stream logger
        output_loggers[sid].close()
        del output_loggers[sid]

        log.removeHandler(log.handlers[1])

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
    if 'job' in session:
        job_output =''

        if session.sid in output_loggers:
            job_output = output_loggers[session.sid].getvalue()  

        return render_template("jobstatus.htm", **{ **dict(session), 'job_output':job_output }) 
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


@app.route('/status', methods=['GET'])
def job_status():
    if 'status' in session and session['status'] is 'running':
        return Response( json.dumps({
                **dict(session),
                'output': output_loggers[session.sid].getvalue() if session.sid in output_loggers else 'No output'
            }), mimetype='application/json')

    return Response(json.dumps(dict(session)), mimetype='application/json')

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

        return Response(json.dumps({ 'cancel':'ok' }), 200 
                , mimetype='application/json')
    return Response(json.dumps({ 'cancel':'no-job' }), 200 
            , mimetype='application/json')


if __name__ == "__main__":
    strh = logging.StreamHandler() 
    strh.setLevel(logging.DEBUG)
    log.addHandler(strh)

    mkdir_p(app.config['UPLOAD_FOLDER'])
    app.run(**flask_options)

