

from micropsi_core.world.world import World
from micropsi_core.world.worldadapter import WorldAdapter

class Malmo(World):

	supported_worldapters = ['Steve']

	def __init__(self, filename, *args, **kwargs):
		World.__init__(self, filename, *args, **kwargs)
		self.logger.info("world created.")

		#connect to malmo aand read all initial values.

class Steve(WorldAdapter):

	def __init__(self, world, uid=None, **data):
		super().__init__(world,uid,**data)
		self.datasources = {'inventory' : 0 , 'worldstate' : 0}
		self.datatargets = {'jump': 0, 'move': 0}
		self.agent_host = MalmoPython.AgentHost()

	def pitch(self ):
		pass

	def update_data_sources_and_targets(self):
		
		#do what we need to do
		if self.datatargets['jump'] > 0:
			#ask if it is possible to do the move.
			self.agent_host.sendCommand("jump 1") #get value and put there

		#move
		#for a working exaple: add 1 to data source jumping if jumping was indeed higher than 0.
		#Write to datasources:



#Make the connection with malmo
#Find some way to install malmo in the world, maybe in the world folder. Maybe install it somehow. Ask aroujnd.
#If it depends on the agent. Then put it in the world adapter, otherwise put it in the world.
#try in malmo if you acn have multiple agnet.s
#two kinds of world adapters: worldadapter (has a dictionary of data sources and adata targets)
#And array world adapter, which holds numpy arrays: gives two types of data soruces: flow (high dimendsion arrays) and the usual (float)

#we can create nodetypes in case we cant solve our problems with pipes, neurons etc. (such as change detector which fires anytime it sees a change.)


#flow modules are also custom nodetypes, no exchange of floats but arrays.

#flow modules can do numpy stuff and returns an array
#flow modules can also do theano operations and returns a theano expression.

#find out what to do with all the information it gets from
