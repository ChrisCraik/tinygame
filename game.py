import sys
import time
import random

import network
from entity import *
from config import Config

# Panda3d
import direct.directbase.DirectStart
from direct.task.Task import Task
from panda3d.core import WindowProperties
from panda3d.core import CollisionTraverser
from panda3d.core import Filename,AmbientLight,DirectionalLight
from panda3d.core import PandaNode,NodePath,Camera,TextNode
from panda3d.core import Vec2,Vec3,Vec4,BitMask32
from direct.gui.OnscreenText import OnscreenText
from direct.actor.Actor import Actor
from direct.showbase.DirectObject import DirectObject
import random, sys, os, math

WAIT_TIME = 1
UPDATE_TIME = 0.03

class Controller(DirectObject):
	def __init__(self, parentChar, keyMap):
		assert isinstance(parentChar, Character)
		base.disableMouse()
		self.char = parentChar
		self.keyMap = keyMap
		print 'keymap is',keyMap
		parentChar.node.rotationallyImmune = True

		self.floater = NodePath('floater')
		self.floater.reparentTo(parentChar.node)
		self.floater.setPos(1,0,2)

		base.camera.reparentTo(self.floater)
		base.camera.setPos(0,-5,0)
		base.camera.setH(0)

		print base.camera.getPos(render)

		props = WindowProperties()
		props.setCursorHidden(True)
		base.win.requestProperties(props)

		taskMgr.add(self.controlCamera, 'camera-task')
		self.h = parentChar.node.getH()
		self.p = parentChar.node.getP()

	#the parent of the camera - the character - is angled by the mouse
	def controlCamera(self, task):
		pointer = base.win.getPointer(0)
		x,y = pointer.getX(), pointer.getY()

		if base.win.movePointer(0,100,100):
			self.h -= (x-100) * 0.2
			self.p -= (y-100) * 0.2
		if self.p < -30: self.p = -30
		if self.p > 30: self.p = 30

		#floater is node for pitch control
		self.floater.setP(self.p)

		#char is floater's parent, actually set it's heading
		self.char.node.setH(self.h)

		return task.cont

	def getControl(self):
		move = Vec2(
			self.keyMap['Right']-self.keyMap['Left'],
			self.keyMap['Fore']-self.keyMap['Back'])
		move.normalize()
		return [self.h, self.p, move.getX(), move.getY(), self.keyMap['Jump'], self.keyMap['Duck'], self.keyMap['Shoot']]

class AIController(DirectObject):
	def __init__(self, parentChar):
		assert isinstance(parentChar, Character)
		self.char = parentChar
	def getControl(self):
		targets = [c.node.getPos() for c in CharacterPool.values() if c.nameNode.node().getText()[:3]!='Zom']
		tar, len = None, ()
		charPos = self.char.node.getPos()
		for target in targets:
			length = (target - charPos).length()
			if length < len:
				tar, len = target, length
		h = Vec2(0,1).signedAngleDeg(Vec2(target.getXy() - charPos.getXy()))
		jump = target.getZ() - charPos.getZ() > 0.5
		#print 'zombie looking in direction:', h, 'at', target, charPos
		return [h,0,0,1 if len > 2 else 0,jump,0,0]

class World(DirectObject):
	def __init__(self, args, log):
		self.args = args
		self.log = log
		self.config = Config()
		
		#set up world
		base.win.setClearColor(Vec4(0,0,0,1))
		self.environ = loader.loadModel('models/world')
		self.environ.reparentTo(render)
		self.environ.setPos(0,0,0)
		Character.startPosition = self.environ.find('**/start_point').getPos()
		
		#set up collisions
		Character.collisionTraverser = CollisionTraverser()
		#Character.collisionTraverser.showCollisions(render)
		
		#set up networking
		mode = network.MODE_SERVER if args.server else network.MODE_CLIENT
		self.connection = network.Connection(mode, args=self.args, log=self.log)
		self.sendDeltaT = 0

		#set up local client
		self.control = Controller(self.connection.localUser.char, self.config.controlDict)
		taskMgr.add(self.step, 'world-step')

		#set up characters
		if self.connection.mode == network.MODE_SERVER:
			self.ai = []
			for i in range(1):
				c = Character(name='Zombie')
				self.ai.append(AIController(c))
			print 'INITIALIZING SERVER WITH', len(self.ai), 'ZOMBIES'

	def stepServer(self):
		assert self.connection.mode == network.MODE_SERVER
		network.sendReceive()

		# Execute client user input messages (and local client)
		for control in ([self.control]+self.ai):
			messageData = control.getControl()+[globalClock.getDt()]
			self.connection.readQueue.appendleft(network.Packet(self.connection.localUser, network.CL_UPDATE, messageData, sender=control))
		while self.connection.readQueue:
			packet = self.connection.readQueue.popleft()
			assert packet.opCode == network.CL_UPDATE
			packet.sender.char.applyControl(packet.data, isLocal=(packet.sender.char==self.connection.localUser.char))

		Character.collisionTraverser.traverse(render)
		
		# Simulate server-controlled objects using simulation time from last full pass
		for c in CharacterPool.values():
			c.postCollide()
		for p in ProjectilePool.values():
			if not p.move(globalClock.getDt()):
				ProjectilePool.remove(p)
				del NetEnt.entities[p.id]
				del p

		# For each connected client, package up visible objects/world state and send to client
		self.sendDeltaT += globalClock.getDt()
		entstate = NetEnt.getState()
		for id in ProjectilePool.pool:
			assert id in NetEnt.entities
		if self.sendDeltaT > UPDATE_TIME:
			for user in UserPool.values():
				if user == self.connection.localUser:
					continue
				self.connection.writeQueue.append(network.Packet(user, network.SV_UPDATE, entstate))
			
			#reduce time to next update (but never allow more than 1 update 'owed')
			self.sendDeltaT = min(self.sendDeltaT-UPDATE_TIME, UPDATE_TIME)
		network.sendReceive()
		#TODO: save global state + mark diffs
		NetEnt.getState()

	def stepClient(self):
		assert self.connection.mode == network.MODE_CLIENT

		# sample client input, deltaT, send to server
		self.sendDeltaT += globalClock.getDt()
		if self.sendDeltaT > UPDATE_TIME:
			message = self.control.getControl()+[self.sendDeltaT]
			self.connection.writeQueue.append(network.Packet(self.connection.serverUser, network.CL_UPDATE, message))
			self.sendDeltaT = 0

		network.sendReceive()

		# Use packets to determine visible objects and their state
		while self.connection.readQueue:
			#print 'client received message from server'
			packet = self.connection.readQueue.popleft()
			assert packet.opCode == network.SV_UPDATE
			assert packet.sender == self.connection.serverUser
			NetEnt.setState(packet.data)

	def step(self, task):
		if self.connection.mode == network.MODE_SERVER:
			self.stepServer()
			print time.clock()
		else:
			self.stepClient()
			print time.clock() + network.deltaClock

		# orient the sprites correctly
		for item in CharacterPool.values()+ProjectilePool.values():
			if item.sprite:
				item.sprite.updateCameraAngle(base.camera)
		#print

		return task.cont