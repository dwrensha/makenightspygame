from flask import *
import twilio.twiml
from twilio.rest import TwilioRestClient
import os 
from pymongo import *
import datetime
import random
import re

debug = False
app = Flask(__name__)


# Twilio account info, to be gotten from Heroku environment variables
account_sid = os.environ['ACCOUNT_SID'] 
auth_token = os.environ['AUTH_TOKEN']
twilionumber = os.environ['TWILIO']
mynumber = os.environ['ME']
# Init twilio
twilioclient = TwilioRestClient(account_sid, auth_token)

# MongoHQ account info, also from Heroku environment variables
mongoclientURL = os.environ['MONGOHQ_URL']
databasename = mongoclientURL.split("/")[-1] #gets the last bit of the URL, which is the database name
# Init Mongo
mongoclient = MongoClient(mongoclientURL)
database = mongoclient[databasename]	#loads the assigned database
# collection = database["phonenumber"] #loads or makes the collection, whichever should happen
players = database["players"]
transcript = database["transcript"]
games = database["games"]


def gameLogic(fromnumber, content):
	check if existing player(fromnumber), return playerNumber
	if false, make newAgent(phonenumber)
	if yes, parse content
	if parser fail, send "huh?" message
	if content has just a number, report friend (reportingAgent, potentialFriend)
	if content has word and number, report enemy (accuser, accusee, codeword)

def checkAgentNumber(phonenumber):
	return agentNumber

def newAgent(phonenumber):
	return True

def reportFriend(reportingAgent, potentialFriend):
	if isFriend:
		message(reportingAgent, "Correct!")
	else:
		message(reportingAgent, "Wrong!")
	return isFriend

def reportEnemy(reportingAgent, potentialEnemy, suspiciousWord):
	if isEnemy:
		message(reportingAgent, "Correct!")
	else:
		message(reportingAgent, "Wrong!")
	return isEnemy

def transcript(content):
	add thing to transcript

@app.route('/', methods=['GET'])
def greet():
	return "hello"

@app.route('/send', methods=['GET'])
def sendToRecipient():
	try:
		message = twilioclient.sms.messages.create(body="hello", to=mynumber, from_=twilionumber)
 	except twilio.TwilioRestException as e:
 		print "twilio error: "+e
 	return "sent message"


@app.route('/twilio', methods=['POST'])
def incomingSMS():
	fromnumber = request.form.get('From', None)
	content = request.form.get('Body', None)
	if fromnumber and content:
		gameLogic(fromnumber, content)
		return "Success!"
	else return "Eh?"