#!/usr/bin/env python3
# coding: utf-8
import io, os, errno, json, tempfile
from flask import Flask, request, redirect, url_for, send_from_directory, render_template, session
from flask.ext.session import Session
from werkzeug import secure_filename
from re import sub

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024
app.config['DEBUG'] = True

ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'dat', 'bax', 'csv'])
SESSION_TYPE = 'redis'

app.config.from_object(__name__)
Session(app)

# Make the upload directory
# Replace this with redis in future
try:
    path=app.config['UPLOAD_FOLDER']
    os.makedirs(app.config['UPLOAD_FOLDER'])
except OSError as exc:
    if exc.errno == errno.EEXIST and os.path.isdir(path): pass
    else: raise

@app.route("/files", methods=['GET'])
def list_uploaded_files():
    return json.dumps([(fil['name'], fil['size']) for fil in session['files']])

@app.route("/clear", methods=['GET'])
def clear_files():
    session['files'] = []
    return 'Files cleared', 200

@app.route("/upload", methods=['PUT'])
def upload():
    fil = request.files['file']
    print('\n'.join(dir(fil)))

    if 'files' not in session.keys():
        session['files'] = []

    def allowed_file(filename):
        return '.' in filename and \
            filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

    if fil and allowed_file(fil.filename):

        original_name = sub('[^a-zA-Z0-9\-_\.]', '', secure_filename(fil.filename))
        temporary_name = next(tempfile._get_candidate_names())

        # Put it on the disk:
        fil.save(os.path.join(app.config['UPLOAD_FOLDER'], temporary_name))

        # Put it in the session (redis)
        #output = io.BytesIO()
        #fil.save(output)

        session['files'].append({
            'original_name'   : original_name,
            'temporary_name'  : temporary_name,
            'size'  : fil.content_length,
            #'bytes' : output,
        })
        print("{} files uploaded".format(len(session['files'])))

        return "File Received{}".format(original_name), 201 #redirect('job')
    return "Bad request. File is not of allowed type: {}".format(original_name), 400


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
    app.run()
