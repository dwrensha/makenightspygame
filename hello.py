from flask import *

debug = False
app = Flask(__name__)

@app.route('/', methods=['GET'])
def greet():
	return "hello"