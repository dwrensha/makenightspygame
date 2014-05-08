import random
import re

def makeLists(inputString, groupSize, numberOfGroups):
	inputList = re.split('\W+', inputString)
	outputList = []
	for i in range(numberOfGroups):
		groupList = []
		for j in range(groupSize):
			groupList.append(inputList.pop(random.randint(0,len(inputList)-1)))
		outputList.append(groupList)
	return outputList
