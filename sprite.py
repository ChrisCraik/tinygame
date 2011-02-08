from pandac.PandaModules import NodePath, PNMImageHeader, PNMImage, Filename, CardMaker, TextureStage, Texture, TransparencyAttrib
from math import log, modf, cos, sin, radians

from direct.directbase import DirectStart
from direct.showbase.DirectObject import DirectObject
from direct.gui.DirectGui import *
from direct.interval.IntervalGlobal import *
from panda3d.core import lookAt
from panda3d.core import GeomVertexFormat, GeomVertexData
from panda3d.core import Geom, GeomTriangles, GeomVertexWriter
from panda3d.core import Texture, GeomNode
from panda3d.core import PerspectiveLens
from panda3d.core import CardMaker
from panda3d.core import Light, Spotlight
from panda3d.core import TextNode
from panda3d.core import Vec3, Vec4, Point3
import sys, os

FRONT=9
BACK=8
SIDE=6
JUMPSIDE=1
FRONTSIDE=10
REARSIDE=11

SpriteId = 0

class Sprite2d:

	class Cell:
		def __init__(self, col, row):
			self.col = col
			self.row = row

		def __str__(self):
			return "Cell - Col %d, Row %d" % (self.col, self.row)

	class Animation:
		def __init__(self, cells, fps):
			self.cells = cells
			self.fps = fps
			self.playhead = 0

	ALIGN_CENTER = "Center"
	ALIGN_LEFT = "Left"
	ALIGN_RIGHT = "Right"
	ALIGN_BOTTOM = "Bottom"
	ALIGN_TOP = "Top"

	TRANS_ALPHA = TransparencyAttrib.MAlpha
	TRANS_DUAL = TransparencyAttrib.MDual
	# One pixel is divided by this much. If you load a 100x50 image with PIXEL_SCALE of 10.0
	# you get a card that is 1 unit wide, 0.5 units high
	PIXEL_SCALE = 20.0

	def __init__(self, image_path, rowPerFace, name=None,\
				  rows=1, cols=1, scale=1.0,\
				  twoSided=False, alpha=TRANS_ALPHA,\
				  repeatX=1, repeatY=1,\
				  anchorX=ALIGN_CENTER, anchorY=ALIGN_BOTTOM):
		"""
		Create a card textured with an image. The card is sized so that the ratio between the
		card and image is the same.
		"""

		global SpriteId
		self.spriteNum = str(SpriteId)
		SpriteId += 1

		scale *= self.PIXEL_SCALE

		self.animations = {}

		self.scale = scale
		self.repeatX = repeatX
		self.repeatY = repeatY
		self.flip = {'x':False,'y':False}
		self.rows = rows
		self.cols = cols

		self.currentFrame = 0
		self.currentAnim = None
		self.loopAnim = False
		self.frameInterrupt = True

		# Create the NodePath
		if name:
			self.node = NodePath("Sprite2d:%s" % name)
		else:
			self.node = NodePath("Sprite2d:%s" % image_path)

		# Set the attribute for transparency/twosided
		self.node.node().setAttrib(TransparencyAttrib.make(alpha))
		if twoSided:
			self.node.setTwoSided(True)

		# Make a filepath
		self.imgFile = Filename(image_path)
		if self.imgFile.empty():
			raise IOError, "File not found"

		# Instead of loading it outright, check with the PNMImageHeader if we can open
		# the file.
		imgHead = PNMImageHeader()
		if not imgHead.readHeader(self.imgFile):
			raise IOError, "PNMImageHeader could not read file. Try using absolute filepaths"

		# Load the image with a PNMImage
		image = PNMImage()
		image.read(self.imgFile)

		self.sizeX = image.getXSize()
		self.sizeY = image.getYSize()

		# We need to find the power of two size for the another PNMImage
		# so that the texture thats loaded on the geometry won't have artifacts
		textureSizeX = self.nextsize(self.sizeX)
		textureSizeY = self.nextsize(self.sizeY)

		# The actual size of the texture in memory
		self.realSizeX = textureSizeX
		self.realSizeY = textureSizeY

		self.paddedImg = PNMImage(textureSizeX, textureSizeY)
		if image.hasAlpha():
			self.paddedImg.alphaFill(0)
		# Copy the source image to the image we're actually using
		self.paddedImg.blendSubImage(image, 0, 0)
		# We're done with source image, clear it
		image.clear()

		# The pixel sizes for each cell
		self.colSize = self.sizeX/self.cols
		self.rowSize = self.sizeY/self.rows

		# How much padding the texture has
		self.paddingX = textureSizeX - self.sizeX
		self.paddingY = textureSizeY - self.sizeY

		# Set UV padding
		self.uPad = float(self.paddingX)/textureSizeX
		self.vPad = float(self.paddingY)/textureSizeY

		# The UV dimensions for each cell
		self.uSize = (1.0 - self.uPad) / self.cols
		self.vSize = (1.0 - self.vPad) / self.rows
	
		self.cards = []
		self.rowPerFace = rowPerFace
		for i in range(len(rowPerFace)):
			card = CardMaker("Sprite2d-Geom")

			# The positions to create the card at
			if anchorX == self.ALIGN_LEFT:
				posLeft = 0
				posRight = (self.colSize/scale)*repeatX
			elif anchorX == self.ALIGN_CENTER:
				posLeft = -(self.colSize/2.0/scale)*repeatX
				posRight = (self.colSize/2.0/scale)*repeatX
			elif anchorX == self.ALIGN_RIGHT:
				posLeft = -(self.colSize/scale)*repeatX
				posRight = 0

			if anchorY == self.ALIGN_BOTTOM:
				posTop = 0
				posBottom = (self.rowSize/scale)*repeatY
			elif anchorY == self.ALIGN_CENTER:
				posTop = -(self.rowSize/2.0/scale)*repeatY
				posBottom = (self.rowSize/2.0/scale)*repeatY
			elif anchorY == self.ALIGN_TOP:
				posTop = -(self.rowSize/scale)*repeatY
				posBottom = 0

			card.setFrame(posLeft, posRight, posTop, posBottom)
			card.setHasUvs(True)
			self.cards.append(self.node.attachNewNode(card.generate()))
			self.cards[-1].setH(i * 360/len(rowPerFace))

		# Since the texture is padded, we need to set up offsets and scales to make
		# the texture fit the whole card
		self.offsetX = (float(self.colSize)/textureSizeX)
		self.offsetY = (float(self.rowSize)/textureSizeY)

		# self.node.setTexScale(TextureStage.getDefault(), self.offsetX * repeatX, self.offsetY * repeatY)
		# self.node.setTexOffset(TextureStage.getDefault(), 0, 1-self.offsetY)
		
		self.texture = Texture()

		self.texture.setXSize(textureSizeX)
		self.texture.setYSize(textureSizeY)
		self.texture.setZSize(1)

		# Load the padded PNMImage to the texture
		self.texture.load(self.paddedImg)

		self.texture.setMagfilter(Texture.FTNearest)
		self.texture.setMinfilter(Texture.FTNearest)

		#Set up texture clamps according to repeats
		if repeatX > 1:
			self.texture.setWrapU(Texture.WMRepeat)
		else:
			self.texture.setWrapU(Texture.WMClamp)
		if repeatY > 1:
			self.texture.setWrapV(Texture.WMRepeat)
		else:
			self.texture.setWrapV(Texture.WMClamp)

		self.node.setTexture(self.texture)
		self.setFrame(0)

	def nextsize(self, num):
		""" Finds the next power of two size for the given integer. """
		p2x=max(1,log(num,2))
		notP2X=modf(p2x)[0]>0
		return 2**int(notP2X+p2x)

	def setFrame(self, frame=0):
		""" Sets the current sprite to the given frame """
		self.frameInterrupt = True # A flag to tell the animation task to shut it up ur face
		self.currentFrame = frame
		self.flipTexture()

	def playAnim(self, animName, loop=False):
		""" Sets the sprite to animate the given named animation. Booleon to loop animation"""
		if not taskMgr.hasTaskNamed("Animate sprite" + self.spriteNum):
			if hasattr(self, "task"):
					taskMgr.remove("Animate sprite" + self.spriteNum)
					del self.task
			self.frameInterrupt = False # Clear any previous interrupt flags
			self.loopAnim = loop
			self.currentAnim = self.animations[animName]
			self.currentAnim.playhead = 0
			self.task = taskMgr.doMethodLater(1.0/self.currentAnim.fps,self.animPlayer, "Animate sprite" + self.spriteNum)

	def createAnim(self, animName, frameCols, fps=12):
		""" Create a named animation. Takes the animation name and a tuple of frame numbers """
		self.animations[animName] = Sprite2d.Animation(frameCols, fps)
		return self.animations[animName]

	def flipX(self, val=None):
		""" Flip the sprite on X. If no value given, it will invert the current flipping."""
		if val:
			self.flip['x'] = val
		else:
			if self.flip['x']:
				self.flip['x'] = False
			else:
				self.flip['x'] = True
		self.flipTexture()
		return self.flip['x']

	def flipY(self, val=None):
		""" See flipX """
		if val:
			self.flip['y'] = val
		else:
			if self.flip['y']:
				self.flip['y'] = False
			else:
				self.flip['y'] = True
		self.flipTexture()
		return self.flip['y']

	def updateCameraAngle(self, cameraNode):
		baseH =  cameraNode.getH(render) - self.node.getH(render)
		degreesBetweenCards = 360/len(self.cards)
		bestCard = int(((baseH)+degreesBetweenCards/2)%360 / degreesBetweenCards)
		#print baseH, bestCard
		for i in range(len(self.cards)):
			if i == bestCard:
				self.cards[i].show()
			else:
				self.cards[i].hide()

	def flipTexture(self):
		""" Sets the texture coordinates of the texture to the current frame"""
		for i in range(len(self.cards)):
			currentRow = self.rowPerFace[i]

			sU = self.offsetX * self.repeatX
			sV = self.offsetY * self.repeatY
			oU = 0 + self.currentFrame * self.uSize
			#oU = 0 + self.frames[self.currentFrame].col * self.uSize
			#oV = 1 - self.frames[self.currentFrame].row * self.vSize - self.offsetY
			oV = 1 - currentRow * self.vSize - self.offsetY
			if self.flip['x'] ^ i==1: ##hack to fix side view
				#print "flipping, i = ",i
				sU *= -1
				#oU = self.uSize + self.frames[self.currentFrame].col * self.uSize
				oU = self.uSize + self.currentFrame * self.uSize
			if self.flip['y']:
				sV *= -1
				#oV = 1 - self.frames[self.currentFrame].row * self.vSize
				oV = 1 - currentRow * self.vSize
			self.cards[i].setTexScale(TextureStage.getDefault(), sU, sV)
			self.cards[i].setTexOffset(TextureStage.getDefault(), oU, oV)

	def clear(self):
		""" Free up the texture memory being used """
		self.texture.clear()
		self.paddedImg.clear()
		self.node.removeNode()

	def animPlayer(self, task):
		if self.frameInterrupt:
			return task.done
		#print "Playing",self.currentAnim.cells[self.currentAnim.playhead]
		self.currentFrame = self.currentAnim.cells[self.currentAnim.playhead]
		self.flipTexture()
		if self.currentAnim.playhead+1 < len(self.currentAnim.cells):
			self.currentAnim.playhead += 1
			return task.again
		if self.loopAnim:
			self.currentAnim.playhead = 0
			return task.again

# Sprite2d(image_path, rows=<rows on sprite sheet>, cols=<columns on sprite sheet>, scale=<optional scale factor>,
#				   twoSided=<option for twosided rendering>, alpha=<TransparencyAttrib>, repeatX=<stretch the card by X, not very compatible with sprite sheets>, repeatY=1,\
#				   anchorX=<"Left, Center, Right">, anchorY=<"top, center, bottom">)

# To manipulate the node, use Sprite2d.node like so:
# Sprite2d.node.reparentTo(<node>)
# Sprite2d.node.setPos(100, 20, 0)

# Sprite2d.setFrame(frame)
# Sprite sheets get their sprites numbered like so:
# -------
# |0|1|2|
# -------
# |3|4|5|
# -------
# Use the sprite number to set the frame

# Sprite2d.createAnim(AnimName, Frames, FPS)
# Create a named animation. Frames is a tuple of frame numbers for the animation. FPS is frames per second.

# Sprite2d.playAnim(AnimName)
# Playback the animation you've created with createAnim

# Sprite2d.clear()
# Clear the texture and pnmimage memory being used and remove the node.
