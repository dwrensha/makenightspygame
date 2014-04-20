from flask import *

@app.route('/', methods=['GET'])
def greet():
	return "hello"