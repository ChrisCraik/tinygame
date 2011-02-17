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

MODE_SERVER = 1
MODE_CLIENT = 2
MAX_PACKET_LENGTH = 1024

TIMEOUT = 5

CL_CONNECT_REQ = 1
CL_UPDATE = 2
SV_UPDATE = 3

clockWeighting = 0.95
deltaClock = 0 #deltaClock is sampled at each packet arrival

class Packet():
	addrToClient = {}
	def __init__(self, receiver, opCode, data, sender=None, sentTime=None):
		self.sender = sender
		#print 'preparing packet to be sent to', receiverID
		self.receiver = receiver
		self.opCode = opCode
		self.data = data
		self.receiver = receiver
		if sentTime:
			self.sentTime = sentTime
	def getState(self):
		return (self.receiver.id, self.opCode, self.data)
	def toString(self):
		return serializer.dumps((self.receiver.id, self.opCode, self.data, time.clock()))
	@staticmethod
	def fromString(sender, str):
		global clockWeighting, deltaClock
		sender.last = time.clock()
		rID,o,p,t = serializer.loads(str)
		
		if rID not in NetEnt.entities:
			localUser = User(rID) # create a receiving user if it doesn't exist
		
		#if client, update local/remote clock diff
		weight = clockWeighting if deltaClock else 0
		deltaClock = weight * deltaClock + (1-weight) * (t-sender.last)
		
		return Packet(NetEnt.entities[rID], o, p, sentTime=t, sender=sender)

def sendReceive():
	asyncore.loop(timeout=0, count=10)

class Connection(asyncore.dispatcher):
	def __init__(self, mode, args, log):
		asyncore.dispatcher.__init__(self)
		self.log = log

		self.readQueue = collections.deque()
		self.writeQueue = collections.deque()
		self.mode = mode

		self.addrToClient = {}

		self.create_socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		if mode == MODE_SERVER:
			self.bind(('',args.port))
			print args.name
			self.serverUser = User(name=args.name)
			self.localUser = self.serverUser
		else:
			self.bind(('',0))
			self.serverUser = User(address=(args.client,args.port))
			self.localUser = None
			self.addrToClient[(args.client,args.port)] = self.serverUser
			self.login(args.name)
			
			## THIS IS A CHEAT - can this be done elsewhere? ##
			packet = self.readQueue.popleft()
			assert packet.opCode == SV_UPDATE
			assert packet.sender.id == self.serverUser.id
			NetEnt.addState(packet.sentTime-0.5, packet.data)
			NetEnt.addState(packet.sentTime, packet.data)
			NetEnt.sampleState(time.clock() + deltaClock - 0.1)
			###################################################

	def login(self, name):
		assert self.mode == MODE_CLIENT and len(self.addrToClient) == 1
		print 'begin login attempt'

		for i in range(10):
			print 'trying to log in...'
			self.writeQueue.append(Packet(self.serverUser, CL_CONNECT_REQ, name))
			time.sleep(1)
			asyncore.loop(count=10,timeout=1)
			if self.serverUser.last != None: #the server's ack'd one of the client's messages
				print 'server acked message!'
				break
		if self.serverUser.last == None:
			# server never ack'd any of our messages!
			assert not 'could not log in!'
		else:
			print 'logged in successfully'

	# everything below should be threadsafe
	def handle_read(self):
		packetStr, address = self.recvfrom(MAX_PACKET_LENGTH)
		
		if address not in self.addrToClient:
			assert self.mode == MODE_SERVER
			self.addrToClient[address] = User(address=address)
		
		packet = Packet.fromString(self.addrToClient[address], packetStr)
		self.log.write('RECEIVED:'+json.dumps(packet.getState())+'\n')
				
		if self.localUser == None:
			#first message from server tells client which user it is
			assert self.mode == MODE_CLIENT
			self.localUser = packet.receiver

		assert self.localUser.id == packet.receiver.id
		
		if packet.opCode == CL_CONNECT_REQ:
			name = packet.data
			print 'seeing client connect from', address, 'named',name
			assert packet.opCode == CL_CONNECT_REQ
			packet.sender.name = name
		else:
			self.readQueue.append(packet)

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