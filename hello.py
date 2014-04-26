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
players = database["players"]	#loads or makes the collection, whichever should happen
transcript = database["transcript"]
games = database["games"]

# ----------- Helpers --------------
# Find the first entry in the collection with the "field" field containing fieldvalue. Return the value of the field named in "response."
def lookup(collection, field, fieldvalue, response):
	return collection.find({field:fieldvalue}, {response:1, "_id":0})[0][response] 
	# "find" returns an array of objects; the first one ought to be the one we want
	# (if more than one thing is possible, look it up manually)

# ----------- Game --------------
# A message containing just a number from a previously unknown phoneNumber should cause the creation of new agent at that phoneNumber with the content as their agentNumber.
# A message containing just a number from a known phoneNumber should check if the number in the content is the number of an agent friendly to the sender.
# A message containing a number and a word from a known phoneNumber should check if the number and word in the content correspond to an enemy agent.
# Anything else should respond with a help message

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
	# first check if it's a known phoneNumber
	if players.find({"phoneNumber": phoneNumber}).count() == 0:
		agentNumber = False
	else:
		agentNumber = lookup(collection=players, field="phoneNumber", fieldvalue=phoneNumber, response="agentNumber")
	return agentNumber

def getPhoneNumber(agentNumber):
	if players.find({"agentNumber": agentNumber}).count() == 0:
		phoneNumber = False
	else:
		phoneNumber = lookup(collection=players, field="agentNumber", fieldvalue=agentNumber, response="phoneNumber")
	return phoneNumber

# At any given time, there is one "active" game in the games collection. "wordlists" contains a list of wordlists.
def assignWords():
	wordlists = lookup(collection=games, field="status", fieldvalue="active", response="wordlists")
	wordlist = random.choice(wordlists)
	return wordlist

# Assign the new agent their wordlist, enter them into the database, and message them their list.
# (Don't try to message them before they're in the DB!)
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
		"points": 0
		})
	success = sendMessage(agentNumber, "welcome [wordlist here]")
	return success

# Check if the potentialFriend is on the same team as the reportingAgent.  If so, congratulate both and assign points.  If not, warn the reportingAgent and demerit them.
def reportFriend(reportingAgent, potentialFriend):
	if isFriend:
		message(reportingAgent, "Correct!")
	else:
		message(reportingAgent, "Wrong!")
	return isFriend

# Check if the suspiciousWord is on the potentialEnemy's wordlist but not the reportingAgent's.  If so, congratulate reportingAgent. If not, chide reportingAgent.  Assign points accordingly.
def reportEnemy(reportingAgent, potentialEnemy, suspiciousWord):
	reportingAgentList = lookup(collection=players, field="agentNumber", fieldvalue=reportingAgent, response="wordlist")
	potentialEnemyList = lookup(collection=players, field="agentNumber", fieldvalue=potentialEnemy, response="wordlist")
	if suspiciousWord in potentialEnemyList:
		if not suspiciousWord in reportingAgentList:
			sendMessage(reportingAgent, "congratulations for useful info")
			awardPoints(reportingAgent, 10)
			awardPoints(potentialEnemy, -10)
			return True
		else:
			sendMessage(reportingAgent, "doesn't that word look familiar to you?")
			return False
	else:
		spuriousReport(suspiciousWord)
		sendMessage(reportingAgent, "we have no such record, be more careful")
		awardPoints(reportingAgent, -3)
		return False


# Send a message to an agent based on their agentNumber (not phoneNumber)
def sendMessage(agentNumber, content):
	phoneNumber = getPhoneNumber(agentNumber)
	if phoneNumber:
		try:
			message = twilioclient.sms.messages.create(body=content, to=phoneNumber, from_=twilionumber)
	 	except twilio.TwilioRestException as e:
	 		content = content + " WITH TWILIO ERROR: " + e
		transcript(agentNumber, content)
		return True
	else:
		return False

def transcript(recipient, content):
	time = datetime.datetime.now()
	transcript.insert({"time":time, "recipient":recipient, "content":content})

# get their points, modify, put them back in the database
def awardPoints(agentNumber, numberofPoints):
	return

# Put a spurious word into the game's record of spurious reports.
def spuriousReport(suspiciousWord):
	return

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