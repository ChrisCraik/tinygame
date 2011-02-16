
from panda3d.core import PandaNode,NodePath,TextNode,Vec3
from panda3d.core import CollisionNode, CollisionRay, CollisionTube, CollisionHandlerQueue, BitMask32
import random
from sprite import Sprite2d

class NetObj:
	def getState(self):
		return {'type':self.__class__.id}

class NetEnt(NetObj):
	entities = {}
	currentID = 1
	types = {}
	def __init__(self, id=None):
		if not id:
			#print 'CREATING (id not asserted)'
			id = NetEnt.currentID
			NetEnt.currentID += 1
		self.id = id
		print 'CREATING: Entities[',self.id,'] = ',self,'type=',self.__class__
		
		assert self.id not in NetEnt.entities
		NetEnt.entities[self.id] = self
	@staticmethod
	def registerSubclass(classval):
		classval.id = len(NetEnt.types)
		NetEnt.types[classval.id] = classval
	@staticmethod
	def getState():
		d = {}
		for id, ent in NetEnt.entities.iteritems():
			#print 'getting state of ent',id,' ',ent
			d[id] = ent.getState()
		return d
	@staticmethod
	def setState(stateDict):
		# first pass at state data: allocate missing entities
		for id, entState in stateDict.iteritems():
			if isinstance(entState, dict):
				if id not in NetEnt.entities:
					print 'creating ent with id',id,'of type',NetEnt.types[entState['type']]
					e = NetEnt.types[entState['type']](id=id)

		# apply state in second pass to allow for entity assignment
		for id, entState in stateDict.iteritems():
			if isinstance(entState, dict):
				NetEnt.entities[id].setState(entState)
				
		for id in NetEnt.entities.keys():
			if id not in stateDict:
				print 'deleting entity', id
				if id in ProjectilePool.pool:
					ProjectilePool.remove(NetEnt.entities[id])
				if id in CharacterPool.pool:
					CharacterPool.remove(NetEnt.entities[id])
				if id in UserPool.pool:
					UserPool.remove(NetEnt.entities[id])
				del NetEnt.entities[id]

class NetPool(NetEnt):
	def __init__(self, id=None):
		NetEnt.__init__(self, id)
		self.pool = set()
	def getState(self):
		return list(self.pool)
	def setState(self, newPool):
		self.pool = set(newPool)
	def add(self, ent):
		self.pool.add(ent.id)
	def remove(self, ent):
		self.pool.remove(ent.id)
	def values(self):
		return [NetEnt.entities[i] for i in self.pool]
NetEnt.registerSubclass(NetPool)

## simple usage below
class NetNodePath(NodePath):
	def __init__(self, node):
		NodePath.__init__(self, node)
		self.rotationallyImmune = False
	def getState(self):
		pos = self.getPos()
		return [str(self.getParent()),(pos[0],pos[1],pos[2]),self.getH()]
	def setState(self, data):
		par,pos,h = data
		#self.setParent(par) #todo: fix
		self.setPos(pos[0],pos[1],pos[2])
		if not self.rotationallyImmune:
			self.setH(h)

ProjectilePool = NetPool()
class Projectile(NetEnt):
	def __init__(self, parentNode=None, id=None):
		NetEnt.__init__(self, id)
		self.node = NetNodePath(PandaNode('projectile'))
		if parentNode:
			self.node.setPos(parentNode.getPos() + (0,0,1))
			self.node.setHpr(parentNode.getHpr())
		self.node.reparentTo(render)
		ProjectilePool.add(self)
		#print 'there are',len(ProjectilePool.values()),'projectiles'
		self.flyTime = 0
		
		self.sprite = Sprite2d('missile.png', rows=3, cols=1, rowPerFace=(0,1,2,1), anchorY=Sprite2d.ALIGN_CENTER)
		self.sprite.node.reparentTo(self.node)

		# collision
		self.collisionHandler = CollisionHandlerQueue()
		# set up 'from' collision - for detecting char hitting things
		self.fromCollider = self.node.attachNewNode(CollisionNode('fromCollider'))
		self.fromCollider.node().addSolid(CollisionRay(0,0,0,0,1,0))
		self.fromCollider.node().setIntoCollideMask(BitMask32.allOff())
		self.fromCollider.node().setFromCollideMask(BitMask32.bit(1))
		#self.fromCollider.show()
		Character.collisionTraverser.addCollider(self.fromCollider,self.collisionHandler)

	def getState(self):
		dataDict = NetObj.getState(self)
		dataDict[0] = self.node.getState()
		return dataDict
	def setState(self, dataDict):
		self.node.setState(dataDict[0])
	def move(self, deltaT):
		self.node.setY(self.node, 20*deltaT)
		self.flyTime += deltaT
		return self.flyTime < 4
	def postCollide(self):
		ch = self.collisionHandler
		entries = [ch.getEntry(i) for i in range(ch.getNumEntries())]
		entries.sort(lambda x,y: cmp(y.getSurfacePoint(render).getZ(),
		                             x.getSurfacePoint(render).getZ()))
		if len(entries) > 0:
			zDelta = entries[0].getSurfacePoint(render)
	def __del__(self):
		#print 'PROJECTILE BEING REMOVED'
		self.node.removeNode()
NetEnt.registerSubclass(Projectile)


CharacterPool = NetPool()
class Character(NetEnt):
	startPosition = None
	collisionTraverser = None
	def __init__(self, name='NONAME', id=None):
		NetEnt.__init__(self, id)
		self.node = NetNodePath(PandaNode('A Character'))
		if not id:
			self.spawn()
		self.node.reparentTo(render)
		CharacterPool.add(self)
		self.vertVelocity = None
		
		self.sprite = Sprite2d("origsprite.png", rows=3, cols=5, rowPerFace=(0,1,2,1))
		self.sprite.createAnim("walk",(1,0,2,0))
		self.sprite.node.reparentTo(self.node)
		
		# set up character's name label
		self.nameNode = NodePath(TextNode('Char Name'))
		self.nameNode.node().setText(name)
		self.nameNode.node().setAlign(TextNode.ACenter)
		self.nameNode.node().setCardColor(0.2, 0.2, 0.2, 0.5)
		self.nameNode.node().setCardAsMargin(0, 0, 0, 0)
		self.nameNode.node().setCardDecal(True)
		self.nameNode.setZ(1.7)
		self.nameNode.setScale(0.2)
		self.nameNode.setBillboardAxis()
		self.nameNode.reparentTo(self.node)

		# collision
		self.collisionHandler = CollisionHandlerQueue()
		# set up 'from' collision - for detecting char hitting things
		self.fromCollider = self.node.attachNewNode(CollisionNode('fromCollider'))
		self.fromCollider.node().addSolid(CollisionRay(0,0,2,0,0,-1))
		self.fromCollider.node().setIntoCollideMask(BitMask32.allOff())
		self.fromCollider.node().setFromCollideMask(BitMask32.bit(0))
		#self.fromCollider.show()
		Character.collisionTraverser.addCollider(self.fromCollider,self.collisionHandler)
		
		# set up 'into' collision - for detecting things hitting char
		self.intoCollider = self.node.attachNewNode(CollisionNode('intoCollider'))
		self.intoCollider.node().addSolid(CollisionTube(0,0,1,0,0,0,0.5))
		self.intoCollider.node().setIntoCollideMask(BitMask32.bit(1))
		self.intoCollider.node().setFromCollideMask(BitMask32.allOff())
		#self.intoCollider.show()

		self.oldPosition = self.node.getPos()
		self.collisionZ = self.node.getZ()
		
		# set up weapons
		self.sinceShoot = 0
		
	def spawn(self):
		#spawn randomly near startPosition, or another character
		startPos = random.choice([c.node.getPos() for c in CharacterPool.values()] + [Character.startPosition])
		self.node.setPos(startPos + Vec3(random.uniform(-3,3),random.uniform(-3,3),3))
		
	def __del__(self):
		print 'CHARACTER BEING REMOVED'
		self.node.removeNode()

	def getState(self):
		dataDict = NetObj.getState(self)
		dataDict[0] = self.node.getState()
		dataDict[1] = self.nameNode.node().getText()
		dataDict[2] = self.vertVelocity != None
		return dataDict
	def setState(self, dataDict):
		oldPos = self.node.getPos()
		self.node.setState(dataDict[0])
		self.nameNode.node().setText(dataDict[1])
		self.animate(oldPos, self.node.getPos())
	def animate(self, oldPos, newPos):
		if self.vertVelocity:
			self.sprite.setFrame(3)
		elif (newPos - oldPos).length() > 0.001:
			self.sprite.playAnim("walk", loop=True)
		else:
			self.sprite.setFrame(0)

	def applyControl(self, controlData, isLocal):
		h, p, deltaX, deltaY, jump, duck, shoot, deltaT = controlData
		if not isLocal:
			self.node.setH(h) # also setP(p) if you want char to pitch up and down

		self.oldPosition = self.node.getPos()
		self.deltaT = deltaT

		speed = 10 if self.nameNode.node().getText()[:3]!='Zom' else 3
		# handle movement
		self.node.setX(self.node, deltaX * speed * deltaT)
		self.node.setY(self.node, deltaY * speed * deltaT)
		
		#handle jumping input
		if jump and self.vertVelocity == None:
			self.vertVelocity = 10
		
		#handle SHOOT
		self.sinceShoot += deltaT
		if shoot and self.sinceShoot > 0.5:
			self.sinceShoot = 0
			p = Projectile(self.node)

	def postCollide(self):
		ch = self.collisionHandler
		entries = [ch.getEntry(i) for i in range(ch.getNumEntries())]
		entries.sort(lambda x,y: cmp(y.getSurfacePoint(render).getZ(),
		                             x.getSurfacePoint(render).getZ()))
		updateReject = True
		updateZ = None
		
		if len(entries) > 0:
			zDelta = entries[0].getSurfacePoint(render).getZ() - self.oldPosition.getZ()
			yDelta = (self.node.getPos() - self.oldPosition).length()
			
			if zDelta < yDelta*1.8 + 0.0001:
				# allow movement up the slope
				self.collisionZ = entries[0].getSurfacePoint(render).getZ()
				updateReject = False
		
		if updateReject:
			# either nothing to stand on, or floor was too steep
			self.node.setPos(self.oldPosition)

		newZ = self.collisionZ
		if self.vertVelocity != None:
			jumpZ = self.node.getZ() + self.vertVelocity * self.deltaT
			if jumpZ > self.collisionZ:
				self.vertVelocity -= 40 * self.deltaT
				self.collisionZ = jumpZ
			else:
				self.vertVelocity = None
			newZ = max(newZ,jumpZ)
		elif self.node.getZ() - 0.1 > newZ:
			newZ = self.node.getZ() - 0.1
			self.vertVelocity = 0
		self.node.setZ(newZ)
		# animate the sprite
		self.animate(self.node.getPos(),self.oldPosition)
NetEnt.registerSubclass(Character)

UserPool = NetPool()
class User(NetEnt):
	def __init__(self, id=None, address=None, remoteAck=None, localAck=None, name='NONAME'):
		NetEnt.__init__(self, id)
		self.points = 0
		if address:
			self.address = address
			self.remoteAck = remoteAck # most recent message they've acked
			self.localAck = localAck   # most recent message from them I've acked
		self.last = None
		if not id:
			# as client never create member NetEnt, it will be passed from server.
			self.char = Character(name)
		UserPool.add(self)
		
	def __del__(self):
		print 'USER BEING REMOVED'
		
	def getState(self):
		dataDict = NetObj.getState(self)
		try:
			dataDict[0] = self.char.id
		except AttributeError:
			dataDict[0] = None
		dataDict[1] = self.points
		return dataDict
	def setState(self, dataDict):
		self.char = NetEnt.entities[dataDict[0]]
		self.points = dataDict[1]
NetEnt.registerSubclass(User)

import rencode
if __name__ == '__main__':
	#common
	chars = NetPool()
	
	#client
	state = {1:[2,3], 2:{'type':1, 0:('(empty)',[0.1,0.2,0.3]), 1:'charname'}}
	strstate = rencode.dumps(state)
	print len(strstate)
	print strstate
	state = rencode.loads(strstate)
	NetEnt.setState(state)
	
	#server
	#for i in range(10):
	#	chars.add(Character())
	print NetEnt.entities
	print NetEnt.types
	x = NetEnt.getState()

	print len(rencode.dumps(x))
	print x
