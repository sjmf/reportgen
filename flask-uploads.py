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
    return render_template("upload.htm")

@app.route("/files", methods=['GET', 'POST'])
def list_uploaded_files():
    print(session)
    if 'files' in session:
        return Response(
                json.dumps( [fil for fil in session['files']] ),
                mimetype='application/json')
    else:
        return Response( '[]', 
                mimetype='application/json')

@app.route("/clear", methods=['GET', 'POST'])
def clear_files():
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

        return "File Received: {}".format(original_name), 200#1 #redirect('job')
    return "File type '{}' is not allowed.".format(original_name.split('.')[1]), 401


@app.route('/job', methods=['GET', 'POST'])
def status():
    fil = request.files['file']
    return render_template("jobstatus.htm")


if __name__ == "__main__":
    mkdir_p(app.config['UPLOAD_FOLDER'])
    app.run(**flask_options)

