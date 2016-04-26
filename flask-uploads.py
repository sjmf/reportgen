#!/usr/bin/env python3
# coding: utf-8
import io, os, errno, re, json, tempfile
from flask import Flask, request, redirect, url_for, send_from_directory, render_template, session
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

# Make the upload directory
# Replace this with redis in future
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path): pass
        else: raise

def escape_filename(filename):
    return re.sub('[^a-zA-Z0-9\-_\.]', '', secure_filename(filename))

@app.route("/files", methods=['GET', 'POST'])
def list_uploaded_files():
    print(session)
    if 'files' in session:
        return json.dumps([(fil['original_name'], fil['size']) for fil in session['files']])
    else:
        return '[]'

@app.route('/files/<path:path>', methods=['DELETE'])
def delete_file(path):
    os.remove(secure_filename(path))
    return 'File deleted', 200

@app.route("/clear", methods=['GET', 'POST'])
def clear_files():
    session['files'] = []
    return 'Files cleared', 200

@app.route('/upload', methods=['POST'])
def upload_file():
    return 'OK', 200
    if request.method == 'POST' or request.method == 'PUT':
        fil = request.files['file']
        if fil and allowed_file(fil.filename):
            filename = secure_filename(fil.filename)
            fil.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return  'OK',200

    return 'NO', 401

#@app.route("/upload", methods=['PUT'])
#def upload():
#    fil = request.files['file']
#    print('\t'.join(fil))
#
#    if 'files' not in session:
#        session['files'] = []
#
#    original_name = escape_filename(fil.filename)
#    temporary_name = next(tempfile._get_candidate_names())
#    file_extension = original_name.rsplit('.', 1)[1] if '.' in original_name else ''
#
#    if fil and file_extension in ALLOWED_EXTENSIONS:
#        # Put it on the disk:
#        fil.save(os.path.join(app.config['UPLOAD_FOLDER'], temporary_name))
#
#        # Put it in the session (redis- experimental)
#        #output = io.BytesIO()
#        #fil.save(output)
#
#        session['files'].append({
#            'original_name'   : original_name,
#            'temporary_name'  : temporary_name,
#            'file_extension'  : file_extension,
#            'size'  : fil.content_length,
#            #'bytes' : output,
#        })
#        print("{} files uploaded".format(len(session['files'])))
#
#        return "File Received: {}".format(original_name), 200#1 #redirect('job')
#    return "File type '{}' is not allowed.".format(original_name.split('.')[1]), 400


@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template("upload.htm")

@app.route('/job', methods=['GET', 'POST'])
def status():
    return render_template("jobstatus.htm")

# Debugging methods - delete these and host from nginx
@app.route('/js/<path:path>')
def send_js(path):
    return send_from_directory('js', path)
@app.route('/css/<path:path>')
def send_css(path):
    return send_from_directory('css', path)
@app.route('/fonts/<path:path>')
def send_font(path):
    return send_from_directory('fonts', path)


if __name__ == "__main__":
    mkdir_p(app.config['UPLOAD_FOLDER'])
    app.run(**flask_options)

