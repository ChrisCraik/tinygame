from direct.gui.DirectGui import *
from pandac.PandaModules import *
import string
import time
import sys

itemHeight = 1.2
numItems = 7
width = 8

data = {
	'Controls':{
		'Jump':'space',
		'Fore':'w',
		'Left':'a',
		'Right':'s',
		'Back':'d',
		'Shoot':'mouse1',
		'Duck':'c',
		},
	'Peaceful':True,
	}

from direct.showbase.DirectObject import DirectObject
class Config(DirectObject):
	def startRemapKey(self, remapFunc, oldValue):
		if 'REMAPINFO' not in self.funcMap:
			print 'remapping', remapFunc, oldValue
			self.funcMap['REMAPINFO'] = remapFunc, time.clock()
			self.buttonMap[remapFunc]['text'] = remapFunc + ': Press Key!'
			self.buttonMap[remapFunc].setText()

	def finishRemapKey(self, remapKey, remapFunc):
		print 'mapping',remapKey,'to',remapFunc
		# unmap key from old binding, if it had one
		oldFunc = self.keyMap.pop(remapKey, None)
		if oldFunc:
			self.funcMap[oldFunc] = None
			self.buttonMap[oldFunc]['text'] = oldFunc+': UNMAPPED'
			self.buttonMap[oldFunc].setText()
			if oldFunc != remapFunc:
				print 'Function',oldFunc,'has no mapping!'
		assert remapKey not in self.keyMap
		
		#map key to its new function
		self.funcMap[remapFunc] = remapKey
		self.buttonMap[remapFunc]['text'] = remapFunc + ': ' + remapKey
		self.buttonMap[remapFunc].setText()
		self.keyMap[remapKey]=remapFunc

	def key(self, char, goingDown):
		if char in self.keyMap:
			self.controlDict[self.keyMap[char]] = 1 if goingDown else 0

		#handle potential remapping
		remapFunc, remapTime = self.funcMap.pop('REMAPINFO', (None,None)) # atomic, presumably safe
		if remapFunc:
			if time.clock() - remapTime < 0.1:
				#not ready yet, put it back
				self.funcMap['REMAPINFO'] = remapFunc, remapTime
			else:
				self.finishRemapKey(char, remapFunc)

	def addConfigDict(self, parent, data, depth=0):
		for k,v in data.iteritems():
			if isinstance(v, dict):
				item = DirectFrame(text='----'+k+'----')
			elif isinstance(v, bool):
				item = DirectCheckButton(text=k+': '+str(v))
			elif isinstance(v, str):
				item = DirectButton(text=k+': '+v, command=self.startRemapKey,extraArgs=[k,v])
				self.buttonMap[k]=item
			item['frameSize'] = (-(width-depth), (width-depth),(0.25 - itemHeight/2.0),(0.25 + itemHeight/2.0))
			parent.addItem(item)
			if isinstance(v, dict):
				self.addConfigDict(parent, v, depth+1)

	def __init__(self):
		self.controlDict = {}
		for k in data['Controls'].keys():
			self.controlDict[k] = 0
		self.configList = DirectScrolledList(
			decButton_pos=(0,0,1.5),
			decButton_text = "/\\",
			incButton_pos=(0,0,-(itemHeight*numItems+0.5)),
			incButton_text = "\\/",
			frameSize = (-(width+0.5), (width+0.5), -(itemHeight*numItems+1), 2.5),
			frameColor = (0,0,0, 0.5),
			numItemsVisible = numItems,
			forceHeight = itemHeight,
			itemFrame_frameSize = (-width, width, -(itemHeight*numItems-0.5), 1),
			scale = 0.1)
		
		# keys is an array of all input key names
		keys = [c for c in string.lowercase + string.digits]
		keys += '; \' , . / = \\ space backspace'.split()
		keys += ['mouse'+str(i) for i in range(1,6)]
		keys += ['arrow_'+d for d in 'up down right left'.split()]
		
		# accept keys as general inputs
		for k in keys:
			self.accept(k, self.key, [k,True])
			self.accept(k+'-up', self.key, [k,False])
		
		# map special keys
		self.accept('escape', sys.exit)
		self.accept('f1', self.configList.show)
		self.accept('f2', self.configList.hide)
		
		#funcmap and keymap hold controlInfo, translate generic key presses to functional key presses
		self.buttonMap = {}
		self.funcMap = data['Controls']
		self.keyMap = {}
		for k,v in self.funcMap.iteritems():
			self.keyMap[v] = k
		self.addConfigDict(self.configList, data)
		
		self.configList.hide()

if __name__=='__main__':
	from direct.directbase import DirectStart
	w = Config()
	run()