import re
import cjson

class ShardMap(object):
	def __init__(self, fname=None):
		if fname is None:
			fname = "/etc/lounge/shards.conf"
		self.load_config(fname)
		self.get_db_shard = re.compile(
				r'^shards%2[fF]([\da-fA-F]{8})-([\da-fA-F]{8})%2[fF](.+)$')
	
	def load_config(self, fname):
		self.config = cjson.decode(file(fname).read())
		self.shardmap = self.config["shard_map"]
		self.nodelist = self.config["nodes"]
		self.dupsets = self.config.get("dup_shards", [])
	
	def get_db_from_shard(self, shard):
		"""Strip out the shard index from a shard name.
		Ex: in -- shards/XXXXXXXX-XXXXXXXX/userinfo
		   out -- userinfo
		"""
		return self.get_db_shard.sub(r'\3', shard)

	def get_index_from_shard(self, shard):
		"""Figure out the shard index from key range
		This assumes <# of shards> equal sized key slices
		Future configurations may allow non-uniform ranges
		"""
		low_key = int(self.get_db_shard.sub(r'\1', shard), 16)
		return low_key / int(0x100000000 / len(self.shardmap))
	
	def shards(self, dbname):
		shard_size = 0x100000000 / len(self.shardmap)
		ranges = [[s,s+shard_size-1]
							for s in range(0, 0x100000001 - shard_size, shard_size)]
		ranges[-1][1] = 0xffffffff

		unique_shards = list(reduce(
			lambda acc, dup: acc.difference(dup[1:]),
			self.dupsets,
			set(range(len(self.shardmap)))))
		unique_shards.sort()

		return ["shards%%2F%08x-%08x%%2F%s" % (tuple(ranges[i]) + (dbname,))
						for i in unique_shards]
	
	def nodes(self, shard=None):
		"""Return a list of nodes holding a particular shard.
		Ex: in -- shards/XXXXXXXX-XXXXXXXX/userinfo
		   out -- [http://bfp6:5984/shards%2FXXXXXXXX-XXXXXXXX%2Fuserinfo, http://bfp7:5984/shards...userinfo, http://bfp9:5984/shards...userinfo]

		If shard is not given, return the node list with no db name.
		Ex:
		  out -- [http://bfp6:5984/, http://bfp7:5984/, http://bfp9:5984]
		"""
		if shard is None:
			return [str("http://%s:%d/" % (host, port)) for host, port in self.nodelist]
		else:
			dbname = self.get_db_from_shard(shard)
			shard_index = self.get_index_from_shard(shard)
			# unicode will mess up stuff like curl, so we convert to plain str
			return [str("http://%s:%d/%s" % (host,port,shard)) for host, port in [self.nodelist[i] for i in self.shardmap[shard_index]]]
	
	def primary_shards(self, dbname):
		"""Return the complete URL of each primary shard for a given database.

		Ex: in -- userinfo
		   out -- [http://server1:5984/shards%2F00000000-XXXXXXXX%2Fuserinfo, http://server2:5984/shards...userinfo, http://server1:5984/shards....userinfo, ...]
		"""
		rv = []
		shards = self.shards(dbname)
		for shard_index,shard_nodes in enumerate(self.shardmap):
			host,port = self.nodelist[shard_nodes[0]]
			rv.append(str("http://%s:%d/%s" % (host,port,shards[shard_index])))
		return rv
			
# vi: noexpandtab ts=2 sw=2
