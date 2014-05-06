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
		# "leaving" removes the player from active status
		if re.match("leaving", rawcontent.lower()):
			retireAgent(agentNumber)
		else:
			# chop rawcontent into a list of lowercase words, separating on whitespace and punctuation
			content = re.split('\W+', rawcontent.lower())
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
				if accusee:
					if len(content) == 1:
						reportEnemy(agentNumber, accusee, content[0])
					else:
						sendMessage(agentNumber, "whoa there one word at a time")
				else:
					parserError(agentNumber)

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
		success = sendMessage(agentNumber, "welcome [wordlist here]")
		transcript(content="New agent: "+agentNumber, tag="newagent")
		return

def retireAgent(agentNumber):
	players.update({"agentNumber":agentNumber}, {"$set":{"status":"retired"}})
	transcript(content="Agent retired: "+agentNumber, tag="agentretired")
	sendMessage(agentNumber, "Good work and goodnight, Agent "+agentNumber+"!")
	return

def parserError(agentNumber, rawcontent):
	transcript(content="Agent "+agentNumber+" sent unparseable content: "+rawcontent, tag="parsererror")
	sendMessage(agentNumber, "Pardon? Visit Q if you need help forming reports.")

# Check if the potentialFriend is on the same team as the reportingAgent.  If so, congratulate both, assign points, and list them on each other's successfulContacts.  If not, warn the reportingAgent and demerit them.
def reportFriend(reportingAgent, potentialFriend):
	if not checkFor(players, "agentNumber", potentialFriend):
		sendMessage(reportingAgent, "We don't have records of an agent by that number.")
	else:
		reportingAgentList = lookup(collection=players, field="agentNumber", fieldvalue=reportingAgent, response="wordlist")
		potentialFriendList = lookup(collection=players, field="agentNumber", fieldvalue=potentialFriend, response="wordlist")
		# check to see if their wordlists are the same
		if reportingAgentList is potentialFriendList:
			# but don't let them report the same friend more than once
			existingcontacts = lookup(collection=players, field="agentNumber", fieldvalue=reportingAgent, response="successfulContacts")
			if not potentialFriend in existingcontacts:
				transcript(content="Agents "+reportingAgent+" and "+potentialFriend+" successfully made contact.", tag="successfulcontact")
				sendMessage(reportingAgent, "Correct!")
				addToRecord(reportingAgent, "successfulContacts", potentialFriend)
				awardPoints(reportingAgent, 10)
				sendMessage(potential, "you've been successfully identified by Agent "+reportingAgent)
				addToRecord(potentialFriend, "successfulContacts", reportingAgent)
				awardPoints(potentialFriend, 10)
				return True
			else:
				sendMessage(reportingAgent, "Correct, but you already knew that.")
				return False
		else:
			transcript(content="Agent "+reportingAgent+" incorrectly reported friendly contact with Agent "+potentialFriend, tag="incorrectcontact")
			sendMessage(reportingAgent, "Wrong! (Watch out)")
			awardPoints(reportingAgent, -3)
			return False

# Check if the suspiciousWord is on the potentialEnemy's wordlist but not the reportingAgent's.  If so, congratulate reportingAgent. If not, chide reportingAgent.  Assign points accordingly.
def reportEnemy(reportingAgent, potentialEnemy, suspiciousWord):
	if not checkFor(players, "agentNumber", potentialEnemy):
		message(reportingAgent, "We don't have records of an agent by that number.")
		return False
	else:
		reportingAgentList = lookup(collection=players, field="agentNumber", fieldvalue=reportingAgent, response="wordlist")
		potentialEnemyList = lookup(collection=players, field="agentNumber", fieldvalue=potentialEnemy, response="wordlist")
		previouslyReportedList = lookup(collection=players, field="agentNumber", fieldvalue=reportingAgent, response="reportedEnemyCodes")
		if potentialEnemy+" "+suspiciousWord in previouslyReportedList:
			sendMessage(reportingAgent, "you already sent us that")
		elif suspiciousWord in potentialEnemyList:
			if not suspiciousWord in reportingAgentList:
				sendMessage(reportingAgent, "congratulations for useful info")
				addToRecord(reportingAgent, "reportedEnemyCodes", potentialEnemy+" "+suspiciousWord)
				awardPoints(reportingAgent, 10)
				addToRecord(potentialEnemy, "interceptedTransmits", reportingAgent+" "+suspiciousWord)
				awardPoints(potentialEnemy, -10)
				transcript(content="Agent "+reportingAgent+" caught Agent "+potentialEnemy+" transmitting code: "+suspiciousWord, tag="interceptedtransmit")
				return True
			else:
				sendMessage(reportingAgent, "doesn't that word look familiar to you?")
				transcript(content="Agent "+reportingAgent+" reported Agent "+potentialEnemy+" for the code: "+suspiciousWord+"but that was their own word too.", tag="interceptedfriendlytransmit")
				return False
		else:
			spuriousReport(suspiciousWord)
			addToRecord(reportingAgent, "spuriousReports", potentialEnemy+" "+suspiciousWord)
			sendMessage(reportingAgent, "we have no such record, be more careful")
			awardPoints(reportingAgent, -3)
			transcript(content="Agent "+reportingAgent+" spuriously reported Agent "+potentialEnemy+" for the code: "+suspiciousWord, tag="spuriousreport")
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
		transcript(content="Sent message to "+agentNumber+": "+content, tag="sentmessage")
		return True
	else:
		return False

def transcript(content, tag):
	time = datetime.datetime.now()
	transcript.insert({"time":time, "tag":tag, "content":content})
	print content
	return

# Append to a player's record list (any of "successfulContacts", "interceptedTransmits", "reportedEnemies", or "spuriousReports")
def addToRecord(agentNumber, field, content):
	players.update({"agentNumber":agentNumber}, {"$push":{field:content}})
	return

# Increments player's points by pointAdjustment
def awardPoints(agentNumber, pointAdjustment):
	players.update({"agentNumber":agentNumber}, {"$inc":{"points":pointAdjustment}})
	return

# Append a spurious word onto the game's record of spurious reports.
def spuriousReport(suspiciousWord):
	games.update({"status":"active"}, {"$push":{"spuriousReports":suspiciousWord}})
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
	else: 
		return "Eh?"


@app.route('/leaderboard', methods=['GET'])
def leaderboard():
	spuriousList = lookup(games, "status", "active", "spuriousReports")
	return render_template("leaderboard.html", players = players, spuriousReports = spuriousList)

@app.route('/leatranscript', methods=['GET'])
def transcript():
	return render_template("transcript.html", information = transcript)

#----------Jinja filter-------------------------------------------
@app.template_filter('printtime')
def timeToString(timestamp):
    return str(timestamp)[11:16]


#-----------Run it!----------------------------------------------

if __name__ == "__main__":
	app.run(debug=debug)


# TODO
# re-join the game? No, I will do this by hand if it's necessary