#!/usr/bin/env python3
# coding: utf-8
import io, os, errno, re, json, tempfile, logging, threading
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

'''
    Application Routes
'''
@app.route('/', methods=['GET'])
def index():
    if 'job' in session.keys():
        return redirect('/job')
    return render_template("upload.htm")


@app.route("/files", methods=['GET', 'POST'])
def list_uploaded_files():
    if 'files' in session:
        return Response(
                json.dumps( [fil for fil in session['files']] ),
                mimetype='application/json')
    else:
        return Response( '[]', 
                mimetype='application/json')


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
    fil = request.files['file']

    if 'files' not in session:
        session['files'] = []

    file_info = save_file(fil, ALLOWED_EXTENSIONS)
    if file_info:
        session['files'].append(file_info)
        log.debug("{} files uploaded".format(len(session['files'])))

        return "File Received: {}".format(file_info['original_name']), 200
    return "File type '{}' is not allowed.".format(file_info['file_extension']), 401


# Start worker thread job and capture its output
def start_job():
    ### Create the loggers
    sublogs = [ logging.getLogger(l) for l in ['reporting.py','graphing.py','datahandling.py', __name__] ]
    [ sublog.setLevel(logging.DEBUG) for sublog in sublogs ]

    ### Handle output with a StringIO object
    stream = io.StringIO()
    output_loggers[session.sid] = stream

    [[ sublog.removeHandler(handler) for handler in sublog.handlers ] for sublog in sublogs ]
    ch = logging.StreamHandler(stream)
    ch.setLevel(logging.DEBUG)

    ### Add a formatter:
    #fmt = logging.Formatter('%(relativeCreated)6d %(threadName)s %(message)s')
    fmt = logging.Formatter('%(message)s')
    ch.setFormatter(fmt)

    ### Add the handler to the loggers
    [ sublog.addHandler(ch) for sublog in sublogs ]

    ### Add another handler for terminal output
    strh = logging.StreamHandler() 
    strh.setLevel(logging.DEBUG)
    [ sublog.addHandler(strh) for sublog in sublogs ]

    log.debug("===============  JOB SETUP  ==================")
    thread = threading.Thread(target=report_worker, args=(session.sid,))
    thread.start()


def geef_session(sid):
    redis = Redis()
    session=pickle.loads(redis.get("session:"+sid))
    return session

def put_session(session, sid):
    redis = Redis()
    redis.set("session:"+sid, pickle.dumps(session)) 

# Report generation worker thread
def report_worker(sid):

    session = geef_session(sid)
    job = session['job']

    log.debug("=============  STARTING WORKER  ==============")
    log.debug("Here's my session:")
    log.debug(pprint.pformat(session))

# TODO: concatenate input datafiles or modify datahandling to take a list (while maintaining backwards compatibility)
    
    ### Expand paths to full location on filesystem 
    output_filename = os.path.join(
        app.config['UPLOAD_FOLDER'], 
        next(tempfile._get_candidate_names()) + '.pdf')
    input_datafile = os.path.join(
        app.config['UPLOAD_FOLDER'], 
        job['files'][0]['temporary_name'])

    if 'map_filename' in job:
        job['map_filename'] = os.path.join(
            app.config['UPLOAD_FOLDER'], 
            job['map_filename'])

    report.report(input_datafile, output_filename, **{**job, 'pdf':True, 'htm':False})
    
    log.debug("=============  WORKER FINISHED  ==============")

    ### Close stream logger
    output_loggers[sid].close()
    del output_loggers[sid]

    # Update session
    session = geef_session(sid)
    session['running'] = False
    session['generated_pdf'] = output_filename
    put_session(session, sid)


@app.route('/generate', methods=['POST'])
def generate_report():
    if 'job' not in session:

        session['job'] = {
            'location'     : escape(request.form['location']),
            'description'  : escape(request.form['description']),
            'files'        : session['files'],
            'sid'          : session.sid,
        }
        if request.files:
            fil = next(iter(request.files.values()))
            file_info = save_file(fil, IMAGE_EXTENSIONS)
            session['job'].update({
                'map_filename' : escape_filename(file_info['temporary_name']),
                'map_file'     : escape_filename(file_info['original_name']),
            })
        session['running'] = True

        start_job()
    
    return redirect('/job')


@app.route('/job', methods=['GET', 'POST'])
def jobs_page():
    if 'job' in session:
        job_output =''
        if session.sid in output_loggers:
            job_output = output_loggers[session.sid].getvalue()  

        return render_template("jobstatus.htm", 
            **{ **session['job'], 
                'job_output': job_output,
                'running': session['running'],
                'done': ('generated_pdf' in session)
            })

    return render_template("jobstatus.htm") 


@app.route('/download', methods=['GET'])
def get_file():
    if 'generated_pdf' in session:
        return send_from_directory(
                app.config['UPLOAD_FOLDER'], 
                session['generated_pdf'].split('/')[-1],
                as_attachment=True,
                attachment_filename=escape_filename(session['job']['location'] +'.pdf'),
                mimetype='application/pdf')

    return "No file", 400

@app.route('/status', methods=['GET'])
def job_status():
    if 'generated_pdf' in session:
        session['job']['done'] = True
        session['running'] = False

        return Response(
            json.dumps({ 'status':'done' })
            , mimetype='application/json')

    elif not session['running']:
        return Response( 
            json.dumps({ 'status':'stopped' })
            , mimetype='application/json')

    return Response( 
            json.dumps({
                'status':'running',
                'output': output_loggers[session.sid].getvalue()
            })
            , 200
            , mimetype='application/json')


@app.route('/cancel', methods=['GET', 'POST'])
def job_cancel():

    if 'job' in session:
        ## TODO: Remove files
        del session['job']
        return 'Job cancelled',200 
    return 'No job running',200


if __name__ == "__main__":
    strh = logging.StreamHandler() 
    strh.setLevel(logging.DEBUG)
    log.addHandler(strh)
    mkdir_p(app.config['UPLOAD_FOLDER'])
    app.run(**flask_options)

