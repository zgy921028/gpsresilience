# -*- coding: utf-8 -*-
"""
Takes the time-series probabilities (generated by likelihood_test_parallel.py) and parses them into events.
Uses a simpmle threshold algorithm.

Created on Fri Jun 27 15:30:51 2014

@author: Brian Donovan (briandonovan100@gmail.com)
"""
from tools import *
#from likelihood_test_parallel import *
from datetime import datetime, timedelta
from Queue import PriorityQueue
from math import sqrt

from collections import defaultdict

#The input files
FEATURE_DIR = "4year_features"					#Generated by extractGridFeaturesParallel.py
OUTLIER_SCORE_FILE = "results/outlier_scores.csv"	#Generated by measureOutliers.py
ZSCORE_FILE = "results/zscore.csv"					#Generated by measureOutliersp.py


#The output files
OUT_UNFILTERED_EVENTS = "results/events_nomerge.csv"
OUT_FILTERED_EVENTS = "results/events_sorted.csv"

OUT_UNFILTERED_EVENTS_KERN = "results/events_nomerge_kern.csv"
OUT_FILTERED_EVENTS_KERN = "results/events_sorted_kern.csv"



#Represents a single segment of time - either an event or a space between events
#Contains a start_id and end_id, which refer to points in time and are INCLUSIVE
#Functions as a node in a doubly-linked-list.  Has methods to merge consecutive segments
class TimeSegment:
	#Simple constructor
	#Arguments:
		#start_id - The start time of this event, refers to an index in the lnp_list
		#end_id - The end time of this event, refers to an index in the lnp_list
	def __init__(self, start_id, end_id, state):
		self.start_id= start_id
		self.end_id = end_id
		self.state = state
		self.prev = None
		self.next = None

	#For debugging	
	def __str__(self):
		return str(self.start_id) + "," + str(self.end_id) + " : " + str(self.state)
	
	#A comparator for sorting times by duration 
	def __cmp__(self, other):
		
		if(other==None):
			return 1
		
		if(self.duration() > other.duration()):
			return 1
		elif(self.duration() < other.duration()):
			return -1
		
		if(self.state < other.state):
			return 1
		elif(self.state > other.state):
			return -1
		
		return 0

	#Compute duration of this segment
	def duration(self):
		return self.end_id - self.start_id + 1 # Start and end are both inclusive, so +1
	
	#Merges a segment with its two neighbors.  Used to "fill gaps" between nearby events.
	#Imagine that the middle (S)pace is merged with its two neighboring (E)vents:
	# From:  E<-->S<-->E<-->S<-->E<-->S<-->E
	#  To :  E<-->S<--------E-------->S<-->E
	#Event, space, event becomes one large event.  Pointers must be updated
	#IMPORTANT : In general, this method should only be called via TimeSegmentList.mergeSegment(), because that method also does some bookkeeping
	#Returns: The newly generated larger segment	
	def mergeWithNeighbors(self):
		#Build the new segment.  there are 3 cases
		if(self.prev==None):
			#This is the first segment - merge with the next segment
			newSegment = TimeSegment(self.start_id, self.next.end_id, self.next.state)
		elif(self.next==None):
			#This is the last segment - merge with the previous segment
			newSegment = TimeSegment(self.prev.start_id, self.end_id, self.prev.state)
		else:
			#General case - merge with the previous AND next segments
			newSegment = TimeSegment(self.prev.start_id, self.next.end_id, self.prev.state)
		
		#Update the links to and from the previous item (if they exist)
		if(self.prev!=None):			
			if(self.prev.prev !=None):
				self.prev.prev.next = newSegment
			newSegment.prev = self.prev.prev
		
		#Update the links to and form the next item (if they e)xist)
		if(self.next!=None):
			if(self.next.next != None):
				self.next.next.prev = newSegment
			newSegment.next = self.next.next

		return newSegment
	
	
#Represents a timeline of many events and spaces between events.
#Contains many TimeSegments. Supports iteration and high-level operations
class TimeSegmentList:
	#Constructor - builds a TimeSegmentList from a list of values and a threshold
	#New TimeSegments are added sequentially each time the value crosses the threshold
	def __init__(self, lnp_list, threshold):
		#prev_state describes whether the threshold is currently above or below the threshold
		prev_state = (lnp_list[0] > threshold) #Grab the first state
		
		prevSegment = None #Stores the last TimeSegment that was created
		self.head = None #Points to the first TimeSegment
		self.iter_segment = None #Used by the __iter__() and next() methods to support Python syntax iteration
		self.lookup_table = {} #A dictionary to support fast lookup of timesegments.  Maps (start_id, end_id) to the relevant TimeSegment object
		
		#Iterate through the list of values
		for i in range(len(lnp_list)):
			#Determine whether the current value is below or above the threshold
			aboveThreshold = lnp_list[i] > threshold
			#If this is different from the previous state, the threshold has been "crossed" - a new TimeSegment will be generated
			if(aboveThreshold != prev_state):

				if(prevSegment==None):
					#This is the first TimeSegment
					start_id = 0
				else:
					#This is not the first TimeSegment - it starts right after the previous one
					start_id = prevSegment.end_id + 1
				
				#Make a new TimeSegment which goes UP TO the point where the threshold was crossed
				segment = TimeSegment(start_id, i-1, prev_state)
				
				#Link it to the previous TimeSegment
				if(prevSegment != None):
					prevSegment.next = segment
				segment.prev = prevSegment
				
				#Update the prev_state and prevSegment
				prev_state = aboveThreshold
				prevSegment = segment
				
				if(self.head == None):
					#If this is the first TimeSegment, it is the head
					self.head = segment
				
				#Add to the lookup_table for fast lookup
				self.lookup_table[(start_id, i-1)] = segment
		
		#When we reach the end of the timeseries, we need to generate one last TimeSegment
		#Same rules as before...
		if(prevSegment==None):
			#This is the first TimeSegment - happens only if the threshold is never crossed
			start_id = 0
		else:
			#This is not the first TimeSegment - it starts right after the previous one
			start_id = prevSegment.end_id + 1
		
		#Make a new TimeSegment and link it to the previous one
		segment = TimeSegment(start_id, i, prev_state)
		segment.prev = prevSegment
		if(prevSegment != None):
			prevSegment.next = segment
		if(self.head == None):
			self.head = segment
		
		#Add to the lookup table
		self.lookup_table[(start_id, i)] = segment
	
	
	#The following two methods are to support Python syntax iteration
	
	#Initialize the iterator - The TimeSegmentList itself serves as the iterator object
	def __iter__(self):
		#Begin iteration at the head
		self.iter_segment = self.head
		return self
	
	#Scan forward through the linked list and return the next element
	def next(self):
		if(self.iter_segment==None):
			raise StopIteration
		else:
			tmp = self.iter_segment
			#Move the iterator forward			
			self.iter_segment = self.iter_segment.next
			#Return the next object
			return tmp
	
	#For debugging
	def __str__(self):
		output = ""
		for segment in self:
			if(self.sorted_dates == None):
				output += str(segment) + '\n'
			else:
				output += str(segment) + " " + str(self.sorted_dates[segment.start_id]) + " " + str(self.sorted_dates[segment.end_id]) + '\n'
		return output
	
	#Wrapper for TimeSegment.mergeWithNeighbors(), which also updates the lookup table (bookkeeping)
	#Arguments:
		#segment - the segment to be merged
	#Returns:
		#The new, large segment that replaces it
	def mergeSegment(self, segment):
		#Remove self and neighbors from lookup table
		del self.lookup_table[segment.start_id, segment.end_id]
		if(segment.prev!=None):
			del self.lookup_table[segment.prev.start_id, segment.prev.end_id]
		if(segment.next!=None):
			del self.lookup_table[segment.next.start_id, segment.next.end_id]
		
		#Actually perform the merge
		new_seg = segment.mergeWithNeighbors()
		
		#Add the NEW segment into the lookup table
		self.lookup_table[new_seg.start_id, new_seg.end_id] = new_seg
		
		#If the first or second elements are merged, the head needs to be updated
		if(new_seg.prev==None):
			self.head = new_seg
		
		#Return the new segment
		return new_seg
	
	#Removes all segments of a certain type, which are shorter than a threshold
	#For example, we might want to remove all non-events which are less than 6 hours
	#Arguments:
		#threshold - The minimum size of timesegments in hours
		#state - are we removing events or non-events.  Specify:
			#True - remove things that are ABOVE the threshold (non-events)
			#False - remove things that are BELOW the threshold (events)
	def removeSmallSegmentsWithState(self, threshold, state):
		current_segment = self.head
		#We must iterate manually (e.g. not Python syntax iteration) to avoid concurrent modification
		while(current_segment != None):
			#Find segments which match the state and are shorter than the threshold
			if(current_segment.state==state and current_segment.duration() < threshold):
				current_segment = self.mergeSegment(current_segment)
			else:
				current_segment = current_segment.next
	
	#Similar to the previous method, but DOES NOT CARE about the type of event
	#Since the order of removal matters, short events are performed first, using a Priority Queue
	#Arguments:
		#threshold - The minimum size of timesegments in hours
	def removeSmallSegmentsInOrder(self, threshold):
		
		#Initialize the Priority Queue with the elements less than the threshold
		pq = PriorityQueue()
		for segment in self:
			if(segment.duration() < threshold):
				pq.put(segment)
		
		#Repeatedly pull the smallest element out of the Priority Queue until it is empty
		while(not pq.empty()):
			segment = pq.get()
			
			#Recall that mergeSegment() deletes items from the TimeSegmentList and the lookup_table
			#But not necessarily from the Priority Queue.  Thus, we need to use the lookup_table to verify
			#That the TimeSegment still exists before we do anything with it
			if((segment.start_id, segment.end_id) in self.lookup_table):
				#If the TimeSegment is valid, merge it with neighbors
				new_seg = self.mergeSegment(segment)
				
				#If this merged TimeSegment is still too small, add it back to the Priority Queue
				if(new_seg.duration() < threshold):
					pq.put(segment)



#Many of the dictionaries used below (e.g. global_pace_timeseries) are keyed by (date, hour, weekday)
#This method converts a datetime object into this tuple
#Arguments:
	#d - a datetime object
#Returns:
	# a tuple (date_string, hour, weekday)
WEEKDAY_STRINGS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
def keyFromDatetime(d):
	date_string = str(d).split()[0]
	hour = d.hour
	weekday = WEEKDAY_STRINGS[d.weekday()]
	return (date_string, hour, weekday)
	

#The different trip names, used by the code below
TRIP_NAMES = []
for orig in ['E','U','M','L']:
	for dest in ['E','U','M','L']:
		TRIP_NAMES.append(orig + "->" + dest)

#After an event is detected, this function computes interesting properties from the time-range of that event
#(The duration, min/max global pace deviations, and the worst trip)
#Arguments:
	#start_key - a tuple (date_string, hour, weekday) which describes the start time of the event
	#end_key - a tuple (date_string, hour, weekday) which describes the end time of the event
	#global_pace_timeseries - See likelihood_test_parallel.GlobalPace()
	#expected_pace_timeseries - See getExpectedPace()
	#zscore_Timeseries - See readZScoresTimeseries()
#Returns: A list [start_date, end_date, duration, max_pace_dev, min_pace_dev, worst_trip] describing properties of the event. Breakdonwn:
	#start_date - a datetime object
	#end_date - a datetime object
	#duration - in hours
	#max_pace_dev - the maximum value of observed_pace - expected_pace
	#min_pace_dev - the minimum value of observed_pace - expected_pace
	#worst_trip - the name of the trip which was most frequently the slowest (by zscore.  Voting by hours)
def computeEventProperties(start_key, end_key, global_pace_timeseries, expected_pace_timeseries, zscore_timeseries):
	(date, hour, weekday) = start_key
	start_date = datetime.strptime(date, "%Y-%m-%d") + timedelta(hours = int(hour))
	
	(date, hour, weekday) = end_key
	end_date = datetime.strptime(date, "%Y-%m-%d") + timedelta(hours = int(hour))

	#Compute duration.  Add 1 because start and end times are inclusive
	duration = int((end_date - start_date + timedelta(hours=1)).total_seconds() / 3600)

	max_pace_dev = float('-inf')
	min_pace_dev = float('inf')
	
	
	
	
	#How many times does each trip appear as the worst trip?
	#At the end, the trip with the most votes is declared the worst trip
	worst_trip_votes = defaultdict(int)
	
	#Iterate through the time range of the event.  Note that we add 1 hour to end_date since event date ranges are inclusive
	for d in dateRange(start_date, end_date + timedelta(hours=1), timedelta(hours=1)):
		key = keyFromDatetime(d)
		#Deviation from expected pace
		pace_dev = (global_pace_timeseries[key] - expected_pace_timeseries[key]) / 60.0 #Divide by 60 - convert minutes to seconds
		max_pace_dev = max(max_pace_dev, pace_dev)
		min_pace_dev = min(min_pace_dev, pace_dev)
		
		#Get the standardized pace vector
		std_pace_vector = zscore_timeseries[key]
		
		
		
		
		#Determine the worst trip in this hour
		worst_zscore = float('-inf')
		worst_zscore_id = 0
		for i in range(len(std_pace_vector)):
			if(std_pace_vector[i] > worst_zscore):
				worst_zscore = std_pace_vector[i]
				worst_zscore_id = i
		
		#That worst trip gets one vote
		worst_trip_votes[worst_zscore_id] += 1


	#Figure out which trip type got the most votes as the "worst trip"		
	max_votes = 0
	max_votes_id = 0
	for trip_id in worst_trip_votes:
		if(worst_trip_votes[trip_id] > max_votes):
			max_votes = worst_trip_votes[trip_id]
			max_votes_id = trip_id
			
	
	#Return the event properties
	return [start_date, end_date, duration, max_pace_dev, min_pace_dev, TRIP_NAMES[max_votes_id]]
	
	
#Given a pace timeseries, compute the expected value for each timeslice (based on the weekly periodic pattern)
#This is a leave-one-out estimate (e.g. The expected pace for Friday, January 1st at 8am is the average of all Fridays at 8am EXCEPT for Friday January 1st)
#Arguments:
	#global_pace_timeseries - see likelihood_test_parallel.readGlobalPace()
#Returns:
	#A tuple (expected_pace_timeseries, sd_pace_timeseries).  Breakdown:
		#expected_pace_timeseries - A dictionary keyed by (date, hour, weekday) which contains expected paces for each hour of the timeseries
		#expected_pace_timeseries - A dictionary keyed by (date, hour, weekday) which contains the standard deviation of paces at that hour of the time series
def getExpectedPace(global_pace_timeseries):
	#First computed grouped counts, sums, and sums of squares
	#Note that these are leave-one-IN estimates.  This will be converted to leave-one-out in the next step
	grouped_sum = defaultdict(float)
	grouped_ss = defaultdict(float)	
	grouped_count = defaultdict(float)
	#Iterate through all days, updating the corresponding sums
	for (date, hour, weekday) in global_pace_timeseries:
		grouped_sum[weekday, hour] += global_pace_timeseries[date,hour,weekday]
		grouped_ss[weekday, hour] += global_pace_timeseries[date,hour,weekday] ** 2
		
		grouped_count[weekday, hour] += 1
	
	expected_pace_timeseries = {}
	sd_pace_timeseries = {}
	#Now that the grouped stats are computed, iterate through the timeseries again
	for (date, hour, weekday) in global_pace_timeseries:
		#The updated count, sum, and sum of squares are computed by subtracting the observation at hand
		#i.e. a leave-one-out estimate
		updated_sum = grouped_sum[weekday, hour] - global_pace_timeseries[date, hour, weekday]
		updated_ss = grouped_ss[weekday, hour] - global_pace_timeseries[date, hour, weekday] ** 2
		updated_count = grouped_count[weekday, hour] - 1
		
		#Compute the average and standard deviation from these sums
		expected_pace_timeseries[date, hour, weekday] = updated_sum / updated_count
		sd_pace_timeseries[date, hour, weekday] = sqrt((updated_ss / updated_count) - expected_pace_timeseries[date, hour, weekday] ** 2)
	
	#Return the computed time series dictionaries
	return (expected_pace_timeseries, sd_pace_timeseries)
		




#Saves a TimeSegmentList object to a file, as a table of events and their properties
#Arguments:
	#timeSegments - a TimeSegmentList object
	#zscore_timeseries - see readZScoresTimeseries()
	#global_pace_timeseries - see likelihood_test_parallel.readGlobalPace()
	#out_file - the file where the event table will be saved
def saveEvents(timeSegments, zscore_timeseries, global_pace_timeseries, out_file):
	eventList = []
	#Compute expected pace and variance
	(expected_pace_timeseries, sd_pace_timeseries) = getExpectedPace(global_pace_timeseries)	
	
	#Iterate through the TimeSegments
	for segment in timeSegments:
		#If the segment is above the threshold, it is an event
		if(segment.state==True):
			start_key = timeSegments.sorted_dates[segment.start_id]
			end_key = timeSegments.sorted_dates[segment.end_id]	
			#Compute event properties
			event = computeEventProperties(start_key, end_key, global_pace_timeseries, expected_pace_timeseries, zscore_timeseries)
			#Add to list			
			eventList.append(event)
	
	#Sort events by duration, in descending order
	eventList.sort(key = lambda x: x[2], reverse=True)
	
	#Write events to a CSV file
	w = csv.writer(open(out_file, "w"))
	w.writerow(["start_date", "end_date", "duration", "max_pace_dev", "min_pace_dev", "worst_trip"])
	for event in eventList:
		[start_date, end_date, duration, max_pace_dev, min_pace_dev, worst_trip] = event
		formattedEvent = [start_date, end_date, duration, "%.2f" % max_pace_dev, "%.2f" % min_pace_dev, worst_trip]
		w.writerow(formattedEvent)
	


#Uses time-series features to detect events and describe them
#Arguments:
	#OUTLIER_SCORE - See readLnpTimeseries()
	#zscore_timeseries - See readZScoreTimeseries()
	#global_pace_timeseries - See likelihood_test_parallel.readGlobalPace()
	#min_event_spacing - the minimum length between events before we decide to merge them
	#threshold_quant - A quantile of OUTLIER_SCORE used to detect events.  Lower values are more selective (detect only the most unusual events) and higher values are more sensitive (detect more events)
	#out_file - The filename where the detected events will be saved
def detectEventsSwitching(OUTLIER_SCORE, zscore_timeseries, global_pace_timeseries, unfiltered_out_file, filtered_out_file, min_event_spacing=6, threshold_quant=.05):
	#Sort the keys of the timeseries chronologically	
	sorted_dates = sorted(OUTLIER_SCORE)
	
	#Generate the list of values of R(t)
	lnp_list = []
	for d in sorted_dates:
		lnp_list.append(OUTLIER_SCORE[d])
	
	#Use the quantile to determine the threshold
	threshold = getQuantile(sorted(lnp_list), threshold_quant)
	
	
	#Use the threshold to chop R(t) into a TimeSegmentList of events and non-events
	timeSegments = TimeSegmentList(lnp_list, threshold)
	timeSegments.sorted_dates = sorted_dates


	#Save these events
	saveEvents(timeSegments, zscore_timeseries, global_pace_timeseries, unfiltered_out_file)
	
	#Merge events that are very close together
	#i.e. delete non-events with less than (min_event_spacing) hours between them
	timeSegments.removeSmallSegmentsWithState(min_event_spacing, False)
	
	#Save the filtered events - these are what we really want.
	saveEvents(timeSegments, zscore_timeseries, global_pace_timeseries, filtered_out_file)
	

	


#Read the time-series outlier scores from file.  Note that this file should be generated by measureOutliers.py
#Arguments:
	#filename - the name of the file where outlier scores are saved
#Returns:
	#a dictionary which maps (date, hour, weekday) to the calculated mahalanobis distance
def readOutlierScores(filename):
	r = csv.reader(open(filename, "r"))
	r.next()
	mahal_timeseries={}
	
	for (date,hour,weekday,mahal,lof1,lof3,lof5,lof10,lof20,lof30,lof50,global_pace,expected_pace,sd_pace) in r:
		hour = int(hour)
		mahal_timeseries[(date,hour,weekday)] = float(mahal)

	return mahal_timeseries


#Read the standardized pace vector (zscores) timeseries from file.  Note that this file should be generated by likelihood_test_parallel.py
#Arguments:
	#filename - the file where the zscores file is saved
#Returns:
	#A dictionary which contains the standardized pace vectors (as Numpy matrices), keyed by (date, hour, weekday) 
def readZScoresTimeseries(filename):
	r = csv.reader(open(filename, "r"))
	r.next()
	timeseries = {}
	for line in r:
		(date, hour, weekday) = line[0:3]
		hour = int(hour)
		timeseries[(date,hour,weekday)] = map(float, line[3:])
	return timeseries

#########################################################################################################
################################### MAIN CODE BEGINS HERE ###############################################
#########################################################################################################
if(__name__=="__main__"):

	#Read the previous results from file
	mahal_timeseries = readOutlierScores(OUTLIER_SCORE_FILE)
	global_pace_timeseries = readGlobalPace(FEATURE_DIR)
	zscore_timeseries = readZScoresTimeseries(ZSCORE_FILE)

	#Perform the event detection on the OUTLIER_SCORE, using extra info to describe the events
	#Events are detected as the 5% lowest values of R(t), and events less than 6 hours apart are merged	
	logMsg("Detecting events at 95% bound")
	detectEventsSwitching(mahal_timeseries, zscore_timeseries, global_pace_timeseries, OUT_UNFILTERED_EVENTS, OUT_FILTERED_EVENTS, min_event_spacing=6, threshold_quant=.95)
	logMsg("Done.")

