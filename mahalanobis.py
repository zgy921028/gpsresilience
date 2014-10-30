# -*- coding: utf-8 -*-
"""
Created on Tue Sep 30 19:28:30 2014

@author: Brian Donovan (briandonovan100@gmail.com)
"""
from tools import *
from numpy import transpose, matrix, nonzero, ravel, diag, sqrt, where
from numpy.linalg import inv, eig



#Represents a set of statistics for a group of mean pace vectors
#Technically, it stores the moments, sum(1), sum(x), sum(x**2)
class GroupedStats:
	def __init__(self, group_of_vectors):
		self.count = 0
		self.s_x = 0
		self.s_xxt = 0
		
		#Iterate through mean pace vectors, updating the counts and sums
		for meanPaceVector in group_of_vectors:
			if(allNonzero(meanPaceVector)):
				self.s_x += meanPaceVector
				self.s_xxt += meanPaceVector * transpose(meanPaceVector)
				self.count += 1
	
	#Make a copy of this GroupedStats object
	#returns: A GroupedStats object, identical to this one
	def copy(self):
		#generate an empty GroupedStats
		cpy = GroupedStats([])
		
		#copy values from this GroupedStats
		cpy.count = self.count
		cpy.s_x = matrix(self.s_x)
		cpy.s_xxt = matrix(self.s_xxt)
		
		#return the copy
		return cpy
	
	#Use the GroupedStats to compute the
	#returns:
		#(mean, cov)  Breakdown:
		#mean - A numpy column vector, representing the mean of all observations
		#cov - A numpy matrix, representing the covariance of all observations
	def getMeanAndCov(self):
		#E(x) = sum(x) / n
		mean = self.s_x / self.count
		
		#var(x) = E[x**2] - E[x]**2.  Multiply by n/(n-1) for unbiased covariance correction
		cov = (self.s_xxt / self.count - (mean * transpose(mean))) * (self.count / (self.count - 1))
		
		return (mean, cov)
	
	#If an observation has missing values, we need to take a subset of the dimensions
	#AKA the mean vector now has less than K dimensions where K <= N, and the cov matrix is K x K
	#This method performs the dimension selection
	#Arguments:
		#obs - the observation which may have some missing values (0 is assumed to be missing)
		#returns a tuple containing the selection on these three inputs, as well as the inverse and determinant of the new matrix
	#Returns:
		#A tuple (mean_subset, cov_subset, obs_subset).  Breakdown:
			#mean_subset - a Kx1 vector
			#cov_subset -a KxK matrix
			#obs_subset - a Kx1 vector
	def getIncompleteMeanAndCov(self, obs):
		#First get the full mean and covariance
		(mean, cov) = self.getMeanAndCov()
		
		#Record the indexes with nonzero value
		valid_ids = ravel(nonzero(obs)[0])		
		
		#Perform the selection using Numpy slicing
		mean_subset = mean[valid_ids,:]
		cov_subset = cov[valid_ids,:][:,valid_ids]
		obs_subset = obs[valid_ids]
		
		
		return (mean_subset, cov_subset, obs_subset)		
	
	
	#Generates a leave-1-out estimate of the group stats.
	#In other words, the variables (count, s_x, s_xxt) will calculated as if a given vector is discluded
	#This is faster than re-generating the stats with a set of vectors that does not include "vect"
	#params:
		#vect - the vector to be "left out"
	#returns:
		#a new GroupedStats that does not contain the information from vect
	def generateLeave1Stats(self, vect):
		#copy self
		newStats = self.copy()
		
		#subtract the leave-one-out vector from the sums
		if(allNonzero(vect)):
			#note - vectors with missing data were not used to create the sums
			#so they should not be subtracted
			newStats.count -= 1
			newStats.s_x -= vect
			newStats.s_xxt -= vect * transpose(vect)
		return newStats
	
	#Returns the mahalanobis distance of a vector from the mean
	#This is one way of measuring how much of an outlier that vector is
	#params:
		#vector - A vector to measure
	#returns a positive number representing the mahalanobis distance
	def mahalanobisDistance(self, vect):
		if(allNonzero(vect)):
			(mean, cov) = self.getMeanAndCov()
		else:
			(mean, cov, vect) = self.getIncompleteMeanAndCov(vect)
		try:
			mahal = transpose(vect - mean) * inv(cov) * (vect - mean)
			return sqrt(mahal[0,0])
		except:
			print vect
			(vects, vals) = eig(cov)
			print vects
			print vals
	
	#Computes the element-wise standardized vector (zscores)
	#In other words, each dimension of the vector is compared to the corresponding
	#mean and std. dev.
	#params:
		#vect - a Numpy column vector
	#returns:
		#a new Numppy column vector, but with each dimension standardized
	def standardizeVector(self, vect):
		(mean, cov) = self.getMeanAndCov()
		#Extract the diagonal components of the covariance matrix
		#And put them into a column vector
		independent_variances=(transpose(matrix(diag(cov))))
		
		
		

		
		#Note that the division is done element-wise
		std_vector = (vect-mean)/sqrt(independent_variances)
		
		#Deal with missing data properly
		#find the dimensions in the original vector that have missing data
		invalid_ids = where(vect==0)[0]
		#set these values to 0 in the standardized vector (this is how missing data is encoded)
		std_vector[invalid_ids,]=0
		
		return std_vector
	
	

		
		
#Computes the mahalanobis distance of each vector from the mean
#Using a leave-one-out estimate.  Also computes the element-wise standardized vector (z-scores)
#params:
	#vectors - a list of Numpy vectors
#returns:
	# distances - a list of Mahalanobis distances,  correspondign to the input vectors
	# zscores - a list of standardized vectors, corresponding to the input vectors
def computeMahalanobisDistances(vectors):
	#compute the groupedStats for the vectors	
	groupedStats = GroupedStats(vectors)
	
	distances = []
	zscores = []
	#We want to compute the Mahalanobis distance for each vector
	for vect in vectors:
		#Get the leave-one-out stats
		stats = groupedStats.generateLeave1Stats(vect)
		#stats = groupedStats
		#Use these to compute the mahalanobis distance from this vector, and add to list
		mahalanobisDistance = stats.mahalanobisDistance(vect)
		distances.append(mahalanobisDistance)
		
		#Compute the element-wise standardized vector
		z_vector = stats.standardizeVector(vect)
		zscores.append(z_vector)
		
	#finally, return the computed distances and zscores
	return (distances, zscores)