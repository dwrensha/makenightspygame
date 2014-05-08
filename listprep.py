import random
import re
import string


def makeLists(inputString, groupSize, numberOfGroups):
	inputList = re.split('\W+', inputString)
	outputList = []
	for i in range(numberOfGroups):
		groupList = []
		for j in range(groupSize):
			groupList.append(inputList.pop(random.randint(0,len(inputList)-1)))
		outputList.append(groupList)
	return outputList


def cleanAndList(rawcontent):
	content = re.split('\W+', rawcontent.strip().lower().strip(string.punctuation))
	return content

print cleanAndList("  .heLlo 08")
