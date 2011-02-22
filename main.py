import sys
import time

from panda3d.core import loadPrcFileData, TextNode
import direct.directbase.DirectStart
from direct.gui.DirectGui import *

from game import World

loadPrcFileData('', 'read-raw-mice 1')
loadPrcFileData('', 'show-frame-rate-meter 1')

#from panda3d.core import PStatClient
#PStatClient.connect()

startFrame = DirectFrame()
nameField = DirectEntry(text='', scale=.1, pos=(0,0,-.4), initialText='PLAYERNAME', text_align=TextNode.ACenter, parent=startFrame)
ipField = DirectEntry(text='IP', scale=.1, pos=(0,0,-.6), text_pos=(4,0,0), initialText='127.0.0.1', text_align=TextNode.ACenter, parent=startFrame)
portField = DirectEntry(text='Port', scale=.1, pos=(0,0,-.8), text_pos=(4,0,0), initialText='5353', text_align=TextNode.ACenter, parent=startFrame)

def startWorld(hosting):
	name, ip, port = nameField.get(), ipField.get(), int(portField.get())
	startFrame.destroy()
	
	log = open(time.strftime('LOG-' + ('server' if hosting else 'client') + '-%Y.%m.%d.%H.%M.%S.txt'), 'w')
	try:
		World(hosting, name, ip, port, log=log)
	except:
		print 'Unexpected Error', sys.exc_info()
		log.write('#ERROR:'+str(sys.exc_info())+'/n')
		log.flush()
		sys.exit()
	log.flush()

DirectButton(text='Join Game', scale=.1, pos=(-.8,0,-.6), text_align=TextNode.ALeft, command=startWorld, extraArgs=[False], parent=startFrame)
DirectButton(text='Host Server', scale=.1, pos=(-.8,0,-.8), text_align=TextNode.ALeft, command=startWorld, extraArgs=[True], parent=startFrame)

run()
