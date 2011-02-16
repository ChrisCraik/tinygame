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

SEQUENCE_MAX = 1<<12

# CL_CONNECT: None
# CL_UPDATE: previousSequence, changesSinceLast, controlInfo
# SV_UPDATE: previousSequence, changesSinceLast

CL_CONNECT_REQ = 1
CL_UPDATE = 2
SV_UPDATE = 3

FAKE_DROP_RATE = 0.0

#		message = (client.id, sequenceNr, opCode, client.localAck, messageData)
#
# need: client.id, opCode, systemTime,
#
#

class Packet():
	def __init__(self, receiver, opCode, data):
		self.receiver = receiver
		self.opCode = opCode
		self.data = data
	def __repr__(self):
		serializer.dumps((self.receiver, self.opCode, self.data))
	def __str__(self):
		return str(self.receiver, self.opCode, self.data)
	@staticmethod
	def fromString(str):
		r,o,p = serializer.loads(str)
		return Packet(r,o,p)

def sendReceive():
	asyncore.loop(timeout=0, count=10)

def sequenceMoreRecent(s1, s2):
	if s2 == None:
		return True
	if (s1 > s2):
		return s1 - s2 <= (SEQUENCE_MAX/2)
	else:
		return s2 - s1 > (SEQUENCE_MAX/2)

class Connection(asyncore.dispatcher):
	def __init__(self, mode, args, log):
		asyncore.dispatcher.__init__(self)
		self.log = log

		self.readQueue = collections.deque()
		self.writeQueue = collections.deque()
		self.mode = mode

		self.addrToClient = {}
		self.sequenceNr = 0

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
			sender, sequenceNr, opCode, messageData = self.readQueue.popleft()
			assert opCode == SV_UPDATE
			assert sender == self.serverUser
			lastAck, serverState = messageData
			NetEnt.setState(serverState)
			###################################################
	def incSequence(self):
		self.sequenceNr = (self.sequenceNr + 1) % SEQUENCE_MAX

	def enqueue(self, destinationUser, opCode, messageData):
		if random.random() < FAKE_DROP_RATE:
			return
		self.writeQueue.append((destinationUser, self.sequenceNr, opCode, messageData))

	def login(self, name):
		assert self.mode == MODE_CLIENT and len(self.addrToClient) == 1
		print 'begin login attempt'

		for i in range(10):
			print 'trying to log in...'
			self.enqueue(self.serverUser, CL_CONNECT_REQ, name)
			time.sleep(1)
			asyncore.loop(count=10,timeout=1)
			if self.serverUser.remoteAck != None: #the server's ack'd one of the client's messages
				print 'server acked message!'
				break
		if self.serverUser.remoteAck == None:
			# server never ack'd any of our messages!
			assert not 'could not log in!'
		else:
			print 'logged in successfully'

	# everything below should be threadsafe
	def handle_read(self):
		packet, address = self.recvfrom(MAX_PACKET_LENGTH)
		
		#print 'received', packet, address
		message = serializer.loads(packet)
		self.log.write('RECEIVED:'+json.dumps(message)+'\n')
		
		localid, sequenceNr, opCode, ackRecent, messageData = message
		if self.localUser == None:
			#first message from server tells client which user it is
			assert self.mode == MODE_CLIENT
			self.localUser = User(id=localid)

		assert self.localUser.id == localid
		
		if address not in self.addrToClient:
			name = messageData
			print 'seeing new client from', address, 'named',name
			assert self.mode == MODE_SERVER
			client = User(address=address,
				remoteAck=None,      # most recent of mine they've seen
				localAck=sequenceNr,
				name=name) # most recent of theirs I've seen
			self.addrToClient[address] = client
		else:
			client = self.addrToClient[address]
			#print 'remote just acked', ackRecent, 'last they acked was', client.remoteAck
			if sequenceMoreRecent(sequenceNr, client.localAck):
				client.localAck = sequenceNr
			if sequenceMoreRecent(ackRecent, client.remoteAck):
				client.remoteAck = ackRecent
		client.last = time.clock()
		if opCode != CL_CONNECT_REQ:
			self.readQueue.append((client, sequenceNr, opCode, messageData))

	def handle_error(self):
		self.log.write('#ERROR:'+str(sys.exc_info())+'/n')
		print sys.exc_info()

	def handle_write(self):
		if not self.writeQueue:
			return
		client, sequenceNr, opCode, messageData = self.writeQueue.popleft()
		
		if client.last:
			lastHeard = time.clock() - client.last
			#print 'last heard from', client.id, lastHeard, 'seconds ago.'
			if lastHeard > TIMEOUT:
				print 'connection',client.id,'timed out!'
				
				CharacterPool.remove(client.char)
				del NetEnt.entities[client.char.id]
				del client.char
				
				UserPool.remove(client)
				del NetEnt.entities[client.id]
				del self.addrToClient[client.address] #do we want to do this? Could remember clients!
				del client
				return

		message = (client.id, sequenceNr, opCode, client.localAck, messageData)

		packet = serializer.dumps(message)
		if len(packet) > MAX_PACKET_LENGTH:
			raise ValueError('Message too long')
		self.log.write('SENT:'+json.dumps(message)+'\n')
		#print 'sending', message, 'to', client.address, '(size is',len(packet),')'

		self.sendto(packet, client.address)