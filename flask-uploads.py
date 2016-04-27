#!/usr/bin/env python3
# coding: utf-8
import io, os, errno, re, json, tempfile
from flask import Flask, request, Response, redirect, url_for, send_from_directory, render_template, session
from flask.ext.session import Session
from werkzeug import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024
app.config['DEBUG'] = True

ALLOWED_EXTENSIONS = set(['txt', 'csv', 'bin', 'bax'])
SESSION_TYPE = 'redis'

app.config.from_object(__name__)
Session(app)

flask_options = {
    'host':'0.0.0.0',
    'threaded':True
}

job_running = False

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

'''
    Application Routes
'''
@app.route('/', methods=['GET'])
def index():
    if job_running:
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

    original_name = escape_filename(fil.filename)
    temporary_name = next(tempfile._get_candidate_names())
    file_extension = original_name.rsplit('.', 1)[1] if '.' in original_name else ''

    if fil and file_extension in ALLOWED_EXTENSIONS:
        # Put it on the disk:
        path = os.path.join(app.config['UPLOAD_FOLDER'], temporary_name)
        fil.save(path)
        file_size = os.stat(path).st_size

        # Put it in the session (redis- experimental)
        #output = io.BytesIO()
        #fil.save(output)

        session['files'].append({
            'original_name'   : original_name,
            'temporary_name'  : temporary_name,
            'file_extension'  : file_extension,
            'file_size'       : file_size,
            'content_type'    : fil.content_type
            #'bytes' : output,
        })
        print("{} files uploaded".format(len(session['files'])))

        return "File Received: {}".format(original_name), 200
    return "File type '{}' is not allowed.".format(file_extension), 401

@app.route('/generate', methods=['POST'])
def generate_report():

    location = request.form['location']
    description = request.form['description']
    if request.files:
        fil = next(iter(request.files.values()))
        original_name = escape_filename(fil.filename)
        print(original_name)

    # Process & launch threads
    job_running = True
    
    # If validated OK, redirect to job running page
    return redirect('/job')

@app.route('/job', methods=['GET', 'POST'])
def job_status():
    return render_template("jobstatus.htm")


if __name__ == "__main__":
    mkdir_p(app.config['UPLOAD_FOLDER'])
    app.run(**flask_options)

