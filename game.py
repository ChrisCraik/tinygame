import sys
import time
import random

import network
from entity import *

# Panda3d
import direct.directbase.DirectStart
from direct.task.Task import Task
from panda3d.core import WindowProperties
from panda3d.core import CollisionTraverser,CollisionHandlerPusher
#from panda3d.core import CollisionHandlerQueue,CollisionRay
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
	def __init__(self, parentChar):
		assert isinstance(parentChar, Character)
		base.disableMouse()
		self.char = parentChar

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

		self.keyMap = {'left':0, 'right':0, 'forward':0, 'backward':0, 'jump':0, 'duck':0, 'shoot':0}
		self.accept('escape',         sys.exit)
		self.accept('arrow_left',     self.setKey, ['left',1])
		self.accept('arrow_right',    self.setKey, ['right',1])
		self.accept('arrow_up',       self.setKey, ['forward',1])
		self.accept('arrow_down',     self.setKey, ['backward',1])
		self.accept('arrow_left-up',  self.setKey, ['left',0])
		self.accept('arrow_right-up', self.setKey, ['right',0])
		self.accept('arrow_up-up',    self.setKey, ['forward',0])
		self.accept('arrow_down-up',  self.setKey, ['backward',0])

		self.accept('space',          self.setKey, ['jump',1])
		self.accept('space-up',       self.setKey, ['jump',0])

		self.accept('lshift',         self.setKey, ['duck',1])
		self.accept('lshift-up',      self.setKey, ['duck',0])
		
		self.accept('mouse1',         self.setKey, ['shoot',1])
		self.accept('mouse1-up',      self.setKey, ['shoot',0])
	def setKey(self, key, value):
		self.keyMap[key] = value

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
			self.keyMap['right']-self.keyMap['left'],
			self.keyMap['forward']-self.keyMap['backward'])
		move.normalize()
		return [self.h, self.p, move.getX(), move.getY(), self.keyMap['jump'], self.keyMap['duck'], self.keyMap['shoot']]

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
		jump = target.getZ() > charPos.getZ()
		#print 'zombie looking in direction:', h, 'at', target, charPos
		return [h,0,0,1 if len > 1 else 0,jump,0,0]

class World(DirectObject):
	def __init__(self, args, log):
		self.args = args
		self.log = log
		
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
		self.control = Controller(self.connection.localUser.char)
		taskMgr.add(self.step, 'world-step')

		#set up characters
		if self.connection.mode == network.MODE_SERVER:
			self.ai = []
			for i in range(3):
				c = Character(name='Zombie')
				self.ai.append(AIController(c))
			print 'INITIALIZING SERVER WITH', len(self.ai), 'ZOMBIES'

	def stepServer(self):
		assert self.connection.mode == network.MODE_SERVER
		network.sendReceive()

		# Execute client user input messages (and local client)
		for control in ([self.control]+self.ai):
			self.connection.readQueue.appendleft((control, None, network.CL_UPDATE, control.getControl()+[globalClock.getDt()]))
		while self.connection.readQueue:
			sender, lastAck, opcode, control = self.connection.readQueue.popleft()
			#print sender, lastAck, opcode, control
			assert opcode == network.CL_UPDATE
			sender.char.applyControl(control, isLocal=(sender.char==self.connection.localUser.char))

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
				#print 'client most recent acked message was', user.localAck
				self.connection.enqueue(user, network.SV_UPDATE, (user.localAck, entstate))
			self.connection.incSequence()
			self.sendDeltaT = 0
		network.sendReceive()
		#TODO: save global state + mark diffs
		NetEnt.getState()

	def stepClient(self):
		assert self.connection.mode == network.MODE_CLIENT

		# sample client input, deltaT, send to server
		self.sendDeltaT += globalClock.getDt()
		if self.sendDeltaT > UPDATE_TIME:
			message = self.control.getControl()+[self.sendDeltaT]
			self.connection.enqueue(self.connection.serverUser, network.CL_UPDATE, message)
			self.connection.incSequence()
			self.sendDeltaT = 0
		network.sendReceive()

		# Use packets to determine visible objects and their state
		while self.connection.readQueue:
			#print 'client received message from server'
			sender, sequenceNr, opCode, messageData = self.connection.readQueue.popleft()
			assert opCode == network.SV_UPDATE
			assert sender == self.connection.serverUser
			lastAck, serverState = messageData
			NetEnt.setState(serverState)

	def step(self, task):
		if self.connection.mode == network.MODE_SERVER:
			self.stepServer()
		else:
			self.stepClient()

		# orient the sprites correctly
		for item in CharacterPool.values()+ProjectilePool.values():
			if item.sprite:
				item.sprite.updateCameraAngle(base.camera)
		#print

		return task.cont