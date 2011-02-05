import argparse
parse = argparse.ArgumentParser(description='It\'s some game or something')
group = parse.add_mutually_exclusive_group(required=True)
group.add_argument('--server', action='store_true', default=False)
group.add_argument('--client', metavar='SERVER_ADDR')
parse.add_argument('--port', type=int, default=5353)
parse.add_argument('--password')
parse.add_argument('--name', default='Player')
results = parse.parse_args()


print 'results:', results
from game import World
#from panda3d.core import PStatClient
w = World(args = results)
#PStatClient.connect()
run()
