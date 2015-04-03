from flask import *
import twilio.twiml
from twilio.rest import TwilioRestClient
import os 
from pymongo import *
import datetime
import random
import re
import string
from flask_socketio import SocketIO, emit

debug = False
app = Flask(__name__)

socketio = SocketIO(app)

# ----------- Setup --------------
# Twilio account info, to be gotten from Heroku environment variables
account_sid = os.environ['ACCOUNT_SID'] 
auth_token = os.environ['AUTH_TOKEN']
twilionumber = os.environ['TWILIO']
mynumber = os.environ['ME']
# Init twilio
twilioclient = TwilioRestClient(account_sid, auth_token)

# Port needed for socketio
heroku_port = os.environ['PORT']

# MongoHQ account info, also from Heroku environment variables
mongoclientURL = os.environ['MONGOHQ_URL']
databasename = mongoclientURL.split("/")[-1] #gets the last bit of the URL, which is the database name

# Init Mongo
mongoclient = MongoClient(mongoclientURL)
database = mongoclient[databasename]	#loads the assigned database
players = database["players"]	#loads or makes the collection, whichever should happen
transcripts = database["transcript"]
games = database["games"]

# ----------- Helpers --------------
# Find the first entry in the collection with the "field" field containing fieldvalue. Return the value of the field named in "response."
def lookup(collection, field, fieldvalue, response):
	return collection.find({field:fieldvalue}, {response:1, "_id":0})[0][response] 
	# "find" returns an array of objects; the first one ought to be the one we want
	# (if more than one thing is possible, look it up manually)

def checkFor(collection, field, fieldvalue):
	return collection.find({field: fieldvalue}).count() > 0

def isAgentNumber(word):
	return re.match("\d{2,3}", word)

# ----------- Game --------------
# "leaving" removes the player from active status
# A message containing just a number from a previously unknown phoneNumber should cause the creation of new agent at that phoneNumber with the content as their agentNumber.
# A message containing just a number from a known phoneNumber should check if the number in the content is the number of an agent friendly to the sender.
# A message containing a number and a word from a known phoneNumber should check if the number and word in the content correspond to an enemy agent.
# Anything else should respond with a help message

def gameLogic(phoneNumber, rawcontent):
	agentNumber = getAgentNumber(phoneNumber)
	# unrecognized number should create a new agent, getting agentName from content
	if not agentNumber:
		newAgent(phoneNumber, rawcontent)
		return
	# recognized number goes on to be treated as a game action
	else:
		transcript(content="Agent "+agentNumber+" sent: "+rawcontent, tag="incoming")
		# "leaving" removes the player from active status
		if re.match("leaving", rawcontent.lower()):
			retireAgent(agentNumber)
		else:
			# chop rawcontent into a list of lowercase words, separating on whitespace and punctuation
			content = re.split('\W+', rawcontent.strip().lower().strip(string.punctuation))
			# if there's only one word, treat it as a potential report of friendly contact
			if len(content) == 1:
				if isAgentNumber(content[0]):
					reportFriend(agentNumber, content[0])
				else:
					parserError(agentNumber, rawcontent)
			# otherwise, treat it as a potential enemy intelligence report (one agent name, one suspicious word)
			else:
				accusee = None
				for i in range(len(content)):
					# if any of the words is an agent number, pull it out and store it as the accusee
					if isAgentNumber(content[i]):
						accusee = content.pop(i)
						break
				if accusee:
					if len(content) == 1:
						reportEnemy(agentNumber, accusee, content[0])
					else:
						sendMessage(agentNumber, "Please only report one suspicious word at a time, agent.")
				else:
					parserError(agentNumber, rawcontent)

def getAgentNumber(phoneNumber):
	# first check if it's a known phoneNumber
	if checkFor(players, "phoneNumber", phoneNumber):
		agentNumber = lookup(collection=players, field="phoneNumber", fieldvalue=phoneNumber, response="agentNumber")
		return agentNumber
	else:
		return False

def getPhoneNumber(agentNumber):
	if checkFor(players, "agentNumber", agentNumber):
		phoneNumber = lookup(collection=players, field="agentNumber", fieldvalue=agentNumber, response="phoneNumber")
		return phoneNumber
	else:
		return False

# At any given time, there is one "active" game in the games collection. "wordlists" contains a list of wordlists.
def assignWords():
	wordlists = lookup(collection=games, field="status", fieldvalue="active", response="wordlists")
	wordlist = random.choice(wordlists)
	return wordlist

# Assign the new agent their wordlist, enter them into the database, and message them their list.
# (Don't try to use sendMessage with an agentNumber before they're in the DB!)
def newAgent(phoneNumber, rawcontent):
	content = re.split('\W+', rawcontent.lower())
	agentNumber = content[0]
	if checkFor(players, "agentNumber", agentNumber):
		sendMessage(agentNumber=None, content="That number seems to be taken. Please see Q to sort things out.", phoneNumber=phoneNumber)
		return
	elif not isAgentNumber(agentNumber):
		sendMessage(agentNumber=None, content="I didn't understand that as an agent number. Please see Q to sort things out.", phoneNumber=phoneNumber)
		return
	else:
		wordlist = assignWords()
		players.insert({
			"agentNumber": agentNumber,
			"phoneNumber": phoneNumber,
			"status": "active",
			"words": wordlist,
			"successfulContacts":[],
			"interceptedTransmits":[],
			"reportedEnemyCodes":[],
			"spuriousReports":[],
			"points": 0
			})
		success = sendMessage(agentNumber, "Greetings, Agent "+agentNumber+"! Your code words are as follows: "+", ".join(wordlist))
		transcript(content="New agent: "+agentNumber, tag="newagent")
		socketio.emit("scorechange", {"agentNumber": agentNumber, "points": 0})
		return

def retireAgent(agentNumber):
	players.update({"agentNumber":agentNumber}, {"$set":{"status":"retired"}})
	transcript(content="Agent retired: "+agentNumber, tag="agentretired")
	sendMessage(agentNumber, "Good work and goodnight, Agent "+agentNumber+".")
	return

def parserError(agentNumber, rawcontent):
	transcript(content="Agent "+agentNumber+"\'s message is unparseable: "+rawcontent, tag="parsererror")
	sendMessage(agentNumber, "Pardon? Visit Q if you are having trouble forming reports.")

# Check if the potentialFriend is on the same team as the reportingAgent.  If so, congratulate both, assign points, and list them on each other's successfulContacts.  If not, warn the reportingAgent and demerit them.
def reportFriend(reportingAgent, potentialFriend):
	if reportingAgent == potentialFriend:
		sendMessage(reportingAgent, "Please don't waste HQ's time by reporting yourself.")
	if not checkFor(players, "agentNumber", potentialFriend):
		sendMessage(reportingAgent, "We don't have records of an agent by that number.")
	else:
		reportingAgentList = lookup(collection=players, field="agentNumber", fieldvalue=reportingAgent, response="words")
		potentialFriendList = lookup(collection=players, field="agentNumber", fieldvalue=potentialFriend, response="words")
		# check to see if their wordlists are the same
		if set(reportingAgentList) == set(potentialFriendList):
			# but don't let them report the same friend more than once
			existingcontacts = lookup(collection=players, field="agentNumber", fieldvalue=reportingAgent, response="successfulContacts")
			if not potentialFriend in existingcontacts:
				transcript(content="Agents "+reportingAgent+" and "+potentialFriend+" successfully made contact.", tag="successfulcontact")
				sendMessage(reportingAgent, "Your report of friendly contact with "+potentialFriend+" checks out.  A major commendation to you both.")
				addToRecord(reportingAgent, "successfulContacts", potentialFriend)
				awardPoints(reportingAgent, 10)
				sendMessage(potentialFriend, "Congratulations on establising contact with Agent "+reportingAgent+".")
				addToRecord(potentialFriend, "successfulContacts", reportingAgent)
				awardPoints(potentialFriend, 10)
				return True
			else:
				sendMessage(reportingAgent, "Contact between yourself and Agent "+potentialFriend+" has already been established.")
				return False
		else:
			transcript(content="Agent "+reportingAgent+" incorrectly reported friendly contact with Agent "+potentialFriend, tag="incorrectcontact")
			sendMessage(reportingAgent, "Our records show that Agent "+potentialFriend+" is not on your side.  Be more careful next time!")
			awardPoints(reportingAgent, -2)
			return False

# Check if the suspiciousWord is on the potentialEnemy's wordlist but not the reportingAgent's.  If so, congratulate reportingAgent. If not, chide reportingAgent.  Assign points accordingly.
def reportEnemy(reportingAgent, potentialEnemy, suspiciousWord):
	if reportingAgent == potentialEnemy:
		sendMessage(reportingAgent, "Please don't waste HQ's time by reporting yourself.")
	if not checkFor(players, "agentNumber", potentialEnemy):
		sendMessage(reportingAgent, "We don't have records of an agent by that number.")
		return False
	else:
		reportingAgentList = lookup(collection=players, field="agentNumber", fieldvalue=reportingAgent, response="words")
		potentialEnemyList = lookup(collection=players, field="agentNumber", fieldvalue=potentialEnemy, response="words")
		previouslyReportedList = lookup(collection=players, field="agentNumber", fieldvalue=reportingAgent, response="reportedEnemyCodes")
		if potentialEnemy+" "+suspiciousWord in previouslyReportedList:
			sendMessage(reportingAgent, "Your report of Agent "+potentialEnemy+"\'s use of code \""+suspiciousWord+"\" was already received.  Do not waste HQ's time with duplicate reports.")
		elif suspiciousWord in potentialEnemyList:
			if not suspiciousWord in reportingAgentList:
				sendMessage(reportingAgent, "Good work! Your report of Agent "+potentialEnemy+"\'s use of code \""+suspiciousWord+"\" is valuable intel.")
				addToRecord(reportingAgent, "reportedEnemyCodes", potentialEnemy+" "+suspiciousWord)
				awardPoints(reportingAgent, 3)
				addToRecord(potentialEnemy, "interceptedTransmits", reportingAgent+" "+suspiciousWord)
				awardPoints(potentialEnemy, -2)
				transcript(content="Agent "+reportingAgent+" caught Agent "+potentialEnemy+" transmitting code \""+suspiciousWord+"\"", tag="interceptedtransmit")
				return True
			else:
				sendMessage(reportingAgent, "Doesn't that word look familiar to you? If you mean to report a friendly agent, send only their agent number.")
				transcript(content="Agent "+reportingAgent+" reported Agent "+potentialEnemy+" for code \""+suspiciousWord+"\" but that was their own word too.", tag="interceptedfriendlytransmit")
				return False
		else:
			spuriousReport(suspiciousWord)
			addToRecord(reportingAgent, "spuriousReports", potentialEnemy+" "+suspiciousWord)
			sendMessage(reportingAgent, "\""+suspiciousWord+"\" does not seem to be an enemy code. Be more careful.")
			awardPoints(reportingAgent, -2)
			transcript(content="Agent "+reportingAgent+" spuriously reported Agent "+potentialEnemy+" for the code \""+suspiciousWord+"\"", tag="spuriousreport")
			return False


# Send a message to an agent based on their agentNumber
def sendMessage(agentNumber, content, phoneNumber=None):
	if agentNumber and not phoneNumber:
		phoneNumber = getPhoneNumber(agentNumber)
		if lookup(collection=players, field="agentNumber", fieldvalue=agentNumber, response="status") is "retired":
			transcript(content="Didn't send message to retired "+agentNumber+": "+content, tag="sentmessage")
			return
	if phoneNumber:
		try:
			message = twilioclient.sms.messages.create(body=content, to=phoneNumber, from_=twilionumber)
	 	except twilio.TwilioRestException as e:
	 		content = content + " WITH TWILIO ERROR: " + e
	 	if agentNumber:
			transcript(content="Sent message to "+agentNumber+": "+content, tag="sentmessage")
		else: 
			transcript(content="Sent message to unidentified agent: "+content, tag="sentmessage")
		return True
	else:
		return False

def transcript(content, tag):
	time = datetime.datetime.now()
	transcripts.insert({"time":time, "tag":tag, "content":content})
	socketio.emit('transcript', {"time":time, "tag":tag, "content":content})
	print content
	return

# Append to a player's record list (any of "successfulContacts", "interceptedTransmits", "reportedEnemies", or "spuriousReports")
def addToRecord(agentNumber, field, content):
	players.update({"agentNumber":agentNumber}, {"$push":{field:content}})
	return

# Increments player's points by pointAdjustment
def awardPoints(agentNumber, pointAdjustment):
	players.update({"agentNumber":agentNumber}, {"$inc":{"points":pointAdjustment}})
	socketio.emit("scorechange", {"agentNumber": agentNumber, "points": pointAdjustment})
	return

# Append a spurious word onto the game's record of spurious reports.
def spuriousReport(suspiciousWord):
	games.update({"status":"active"}, {"$push":{"spuriousReports":suspiciousWord}})
	socketio.emit("spurious", suspiciousWord)

	return

# ----------- Web --------------

@app.route('/', methods=['GET'])
def greet():
	return "nothing to see here"

@app.route('/twilio', methods=['POST'])
def incomingSMS():
	phoneNumber = request.form.get('From', None)
	content = request.form.get('Body', None)
	socketio.emit('message', content)
	if phoneNumber and content:
		gameLogic(phoneNumber, content)
		return "Success!"
	else: 
		return "Eh?"


@app.route('/leaderboard', methods=['GET'])
def leaderboard():
	spuriousList = lookup(games, "status", "active", "spuriousReports")
	return render_template("leaderboard.html", players = players, spuriousReports = spuriousList)

@app.route('/leatranscript', methods=['GET'])
def showtranscript():
	return render_template("transcript.html", information = transcripts)

# @app.route('/sockettest', methods=['GET'])
# def testThoseSockets():
# 	return render_template("sockettest.html")

# @app.route('/socketsend', methods=['GET'])
# def sendThatSocket():
# 	print "loaded"
# 	socketio.emit('message', "hello from a get request")
# 	return "success"

@socketio.on('message')
def handle_source():
    socketio.emit('message', "hello from a socket event")


#----------Jinja filter-------------------------------------------
@app.template_filter('printtime')
def timeToString(timestamp):
    return str(timestamp)[11:16]


#-----------Run it!----------------------------------------------

if __name__ == "__main__":
	# app.run(debug=debug)
	socketio.run(app, port=heroku_port)

# TODO
# re-join the game? No, I will do this by hand if it's necessary
# don't let people report themselves (DONE)
# spaces at the beginning of texts
# sweet websocket leaderboard