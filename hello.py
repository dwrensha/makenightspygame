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

# ----------- Setup --------------
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
# collection = database["phoneNumber"] #loads or makes the collection, whichever should happen
players = database["players"]
transcript = database["transcript"]
games = database["games"]

# ----------- Helpers --------------
def lookup(collection, field, fieldvalue, response):
	return collection.find({field:fieldvalue}, {response:1, "_id":0})[0][response] 
	# "find" returns an array of objects; the first one ought to be the one we want
	# (if more than one thing is possible, look it up manually)

# ----------- Game --------------
def gameLogic(phoneNumber, content):
	agentNumber = getAgentNumber(phoneNumber)
	if not agentNumber:
		newAgent(phoneNumber, content)
	else:
		if yes, parse content
		if parser fail, send "huh?" message
		if content has just a number, report friend (reportingAgent, potentialFriend)
		if content has word and number, report enemy (accuser, accusee, codeword)

def getAgentNumber(phoneNumber):
	if players.find({"phoneNumber": phoneNumber}).count() == 0:
		agentNumber = False
	else:
		agentNumber = lookup(collection=players, field="phoneNumber", fieldvalue=phoneNumber, response="agentNumber")
	return agentNumber

def getPhoneNumber(agentNumber):
	return phoneNumber

def assignWords():
	wordlists = lookup(collection=games, field="status", fieldvalue="active", response="wordlists")
	wordlist = random.choice(wordlists)
	return wordlist

def newAgent(phoneNumber, content):
	agentNumber = content
	wordlist = assignWords()
	players.insert({
		"agentNumber": agentNumber,
		"phoneNumber": phoneNumber,
		"active": "True",
		"words": wordlist,
		"successfulContacts":[],
		"interceptedTransmits":[],
		"reportedEnemies":[],
		"spuriousReports":[],
		})
	sendMessage(agentNumber, "welcome!")
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


def sendMessage(agentNumber, content):
	phoneNumber = getPhoneNumber(agentNumber)
	try:
		message = twilioclient.sms.messages.create(body=content, to=phoneNumber, from_=twilionumber)
 	except twilio.TwilioRestException as e:
 		content = content + " WITH TWILIO ERROR: " + e
	transcript(agentNumber, content)
	return True

def transcript(recipient, content):
	time = datetime.datetime.now()
	transcript.insert({"time":time, "recipient":recipient, "content":content})

# ----------- Web --------------

@app.route('/', methods=['GET'])
def greet():
	return "nothing to see here"

@app.route('/twilio', methods=['POST'])
def incomingSMS():
	phoneNumber = request.form.get('From', None)
	content = request.form.get('Body', None)
	if phoneNumber and content:
		gameLogic(phoneNumber, content)
		return "Success!"
	else return "Eh?"