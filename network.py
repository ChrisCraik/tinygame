import time
import asyncore
import collections
import logging
import socket
import random
import sys
from entity import *

# also: json, marshal pickle
import json
import rencode
serializer = rencode

from direct.stdpy import threading

mode = None
MODE_SERVER = 1
MODE_CLIENT = 2
MAX_PACKET_LENGTH = 1024

TIMEOUT = 5

CL_CONNECT_REQ = 1
CL_UPDATE = 2
SV_UPDATE = 3

clockWeighting = 0.95
deltaClock = 0 #deltaClock is sampled at each packet arrival


def getTime():
	if mode == MODE_SERVER:
		return time.clock()
	else:
		return time.clock() + deltaClock

class Packet():
	addrToClient = {}
	def __init__(self, receiver, opCode, data, sender=None, sentTime=None, arriveTime=None):
		self.sender = sender
		#print 'preparing packet to be sent to', receiverID
		self.receiver = receiver
		self.opCode = opCode
		self.data = data
		self.receiver = receiver
		if sentTime:
			self.sentTime = sentTime
		if arriveTime:
			self.arriveTime = arriveTime
	def getState(self):
		return (self.receiver.id, self.opCode, self.data)
	def toString(self):
		global mode, deltaClock
		return serializer.dumps((self.receiver.id, self.opCode, self.data, getTime()))
	@staticmethod
	def fromString(sender, str):
		global mode, clockWeighting, deltaClock
		arriveTime = time.clock()
		rID,o,p,t = serializer.loads(str)
		
		if rID not in NetEnt.entities:
			localUser = User(rID) # create a receiving user if it doesn't exist
		
		if mode == MODE_CLIENT:
			# update local/remote clock diff
			weight = clockWeighting if deltaClock else 0
			deltaClock = weight * deltaClock + (1-weight) * (t-arriveTime)
		else:
			# todo: use timestamp to help remote calculate ping
			pass
		
		return Packet(NetEnt.entities[rID], o, p, sentTime=t, sender=sender, arriveTime=arriveTime)

def sendReceive():
	asyncore.loop(timeout=0, count=10)

class Connection(asyncore.dispatcher):
	def __init__(self, newmode, name, ip, port, log):
		global mode
		mode = newmode
		
		asyncore.dispatcher.__init__(self)
		self.log = log

		self.readQueue = collections.deque()
		self.writeQueue = collections.deque()

		self.addrToClient = {}

		self.create_socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		if mode == MODE_SERVER:
			self.bind(('',port))
			self.serverUser = User(name=name)
			self.localUser = self.serverUser
		else:
			self.bind(('',0))
			self.serverUser = User(address=(ip,port))
			self.localUser = None
			self.addrToClient[(ip,port)] = self.serverUser
			self.login(name)

	def login(self, name):
		assert mode == MODE_CLIENT and len(self.addrToClient) == 1
		print 'begin login attempt'

		for i in range(10):
			print 'trying to log in...'
			self.writeQueue.append(Packet(self.serverUser, CL_CONNECT_REQ, name))
			asyncore.loop(count=10,timeout=1)
			time.sleep(1)
			if self.serverUser.last != None: #the server's ack'd one of the client's messages
				print 'server acked message!'
				break
		if self.serverUser.last == None:
			# server never ack'd any of our messages!
			assert not 'could not log in!'
		else:
			print 'logged in successfully'
		## THIS IS A CHEAT - can this be done elsewhere? ##
		packet = self.readQueue.popleft()
		assert packet.opCode == SV_UPDATE
		assert packet.sender.id == self.serverUser.id
		NetEnt.addGlobalState(packet.sentTime-0.5, packet.data)
		NetEnt.addGlobalState(packet.sentTime, packet.data)
		NetEnt.takeGlobalStateSample(getTime())
		###################################################

	# everything below should be threadsafe
	def handle_read(self):
		packetStr, address = self.recvfrom(MAX_PACKET_LENGTH)
		
		if address not in self.addrToClient:
			assert mode == MODE_SERVER
			self.addrToClient[address] = User(address=address)
		
		packet = Packet.fromString(self.addrToClient[address], packetStr)
		self.log.write('RECEIVED:'+json.dumps(packet.getState())+'\n')
		
		if self.localUser == None:
			assert mode == MODE_CLIENT
			self.localUser = packet.receiver

		assert self.localUser.id == packet.receiver.id
		
		if packet.opCode == CL_CONNECT_REQ:
			name = packet.data
			print 'seeing client connect from', address, 'named',name
			assert packet.opCode == CL_CONNECT_REQ
			packet.sender.char.nameNode.node().setText(name)
		else:
			self.readQueue.append(packet)
		self.addrToClient[address].last = packet.arriveTime

	def handle_error(self):
		self.log.write('#ERROR:'+str(sys.exc_info())+'/n')
		#print sys.exc_info()

	def handle_write(self):
		if not self.writeQueue:
			return
		packet = self.writeQueue.popleft()
		assert isinstance(packet, Packet)
		
		if packet.receiver.last:
			lastHeard = time.clock() - packet.receiver.last
			if lastHeard > TIMEOUT:
				print 'connection',packet.receiver.id,'timed out!'
				
				CharacterPool.remove(packet.receiver.char)
				del NetEnt.entities[packet.receiver.char.id]
				del packet.receiver.char
				
				UserPool.remove(packet.receiver)
				del NetEnt.entities[packet.receiver.id]
				del self.addrTopacket.receiver[packet.receiver.address] #do we want to do this? Could remember clients!
				del packet.receiver
				return

		packetData = packet.toString()
		if len(packetData) > MAX_PACKET_LENGTH:
			raise ValueError('Message too long')
		self.log.write('SENT:'+json.dumps(packet.getState())+'\n')

		self.sendto(packetData, packet.receiver.address)