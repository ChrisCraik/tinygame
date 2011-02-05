import sys
import time
import random

import network
from entity import *

# Panda3d
import direct.directbase.DirectStart
from direct.task.Task import Task
from panda3d.core import WindowProperties
from panda3d.core import CollisionTraverser,CollisionNode
from panda3d.core import CollisionHandlerQueue,CollisionRay
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
	def __init__(self, parentNode):
		base.disableMouse()

		parentNode.rotationallyImmune = True

		self.floater = NodePath("floater")
		self.floater.reparentTo(parentNode)
		self.floater.setPos(1,0,2)

		base.camera.reparentTo(self.floater)
		base.camera.setPos(0,-5,0)
		base.camera.setH(0)

		print base.camera.getPos(render)

		props = WindowProperties()
		props.setCursorHidden(True)
		base.win.requestProperties(props)

		taskMgr.add(self.controlCamera, "camera-task")
		self.h = parentNode.getH()
		self.p = parentNode.getP()

		self.keyMap = {"left":0, "right":0, "forward":0, "backward":0, "jump":0, "duck":0}
		self.accept("escape",         sys.exit)
		self.accept("arrow_left",     self.setKey, ["left",1])
		self.accept("arrow_right",    self.setKey, ["right",1])
		self.accept("arrow_up",       self.setKey, ["forward",1])
		self.accept("arrow_down",     self.setKey, ["backward",1])
		self.accept("arrow_left-up",  self.setKey, ["left",0])
		self.accept("arrow_right-up", self.setKey, ["right",0])
		self.accept("arrow_up-up",    self.setKey, ["forward",0])
		self.accept("arrow_down-up",  self.setKey, ["backward",0])

		self.accept("space",          self.setKey, ["jump",1])
		self.accept("space-up",       self.setKey, ["jump",0])

		self.accept("lshift",         self.setKey, ["duck",1])
		self.accept("lshift-up",      self.setKey, ["duck",0])
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
		self.floater.getParent().setH(self.h)

		return task.cont

	def getControl(self):
		move = Vec2(
			self.keyMap["right"]-self.keyMap["left"],
			self.keyMap["forward"]-self.keyMap["backward"])
		move.normalize()
		#print move
		return [self.h, self.p, move.getX(), move.getY(), self.keyMap["jump"], self.keyMap["duck"]]

speed = 5
class World(DirectObject):
	def __init__(self, args, log):
		self.args = args
		self.log = log
		
		#set up world
		base.win.setClearColor(Vec4(0,0,0,1))
		self.environ = loader.loadModel("models/world")
		self.environ.reparentTo(render)
		self.environ.setPos(0,0,0)
		Character.startPosition = self.environ.find("**/start_point").getPos()
		print 'starting at', Character.startPosition

		#set up networking
		if args.server:
			self.charsMap = {}
			mode = network.MODE_SERVER
			print 'INITIALIZING SERVER'
		else:
			mode = network.MODE_CLIENT
		self.connection = network.Connection(mode, args=self.args, log=self.log)
		self.sendDeltaT = 0

		#setup local client
		self.control = Controller(self.connection.localUser.char.node)
		taskMgr.add(self.step, "world-step")

	def applyControl(self, character, controlData):
		h, p, deltaX, deltaY, jump, duck, deltaT = controlData
		if character != self.connection.localUser.char:
			character.node.setH(h) # also setP(p) if you want char to pitch up and down

		# handle movement
		character.node.setX(character.node, deltaX * speed * deltaT)
		character.node.setY(character.node, deltaY * speed * deltaT)
		
		# handle jumping input
		if jump and character.vertVelocity == None:
			character.vertVelocity = 10
		if character.vertVelocity:
			jumpZ = character.node.getZ() + character.vertVelocity * deltaT
			if jumpZ >= 0:
				character.node.setZ(jumpZ)
				character.vertVelocity -= 40 * deltaT
			else:
				character.node.setZ(0)
				character.vertVelocity = None

		# animate the sprite
		character.animate(deltaX,deltaY)			

	def stepServer(self):
		assert self.connection.mode == network.MODE_SERVER
		network.sendReceive()

		# Execute client user input messages (and local client)
		self.connection.readQueue.appendleft((self.connection.serverUser, None, network.CL_UPDATE, self.control.getControl()+[globalClock.getDt()]))
		while self.connection.readQueue:
			sender, lastAck, opcode, control = self.connection.readQueue.popleft()
			#print sender.id, lastAck, opcode, control
			assert opcode == network.CL_UPDATE
			self.applyControl(sender.char, control)

		# Simulate server-controlled objects using simulation time from last full pass
		#print 'simulating'

		# For each connected client, package up visible objects/world state and send to client
		self.sendDeltaT += globalClock.getDt()
		if self.sendDeltaT > UPDATE_TIME:
			for user in UserPool.values():
				if user == self.connection.localUser:
					continue
				#print 'client most recent acked message was', user.localAck
				self.connection.enqueue(user, network.SV_UPDATE, (user.localAck, NetEnt.getState()))
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
			#print serverState
			NetEnt.setState(serverState)
		#print NetEnt.getState()

	def step(self, task):
		if self.connection.mode == network.MODE_SERVER:
			self.stepServer()
		else:
			self.stepClient()

		# orient the sprites correctly
		for char in CharacterPool.values():
			if char.sprite:
				char.sprite.updateCameraAngle(base.camera)
		#print

		return task.cont