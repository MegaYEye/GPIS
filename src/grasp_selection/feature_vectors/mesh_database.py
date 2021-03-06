from abc import ABCMeta, abstractmethod

class MeshDatabase:
	def object_category_for_key(self, key):
		"""Get an object category for a given object key"""
		if key in self.object_dict_:
			return self.object_dict_[key]
		else:
			return None

	def object_keys(self):
		"""Get a dictionary of objects: keys: object ids, values: object category"""
		return self.object_dict_.keys()

	def object_dict(self):
		"""Get a dictionary of objects: keys: object ids, values: object category"""
		return self.object_dict_

class Cat50ObjectDatabase(MeshDatabase):
	def __init__(self, path_to_index):
		self.create_categories(path_to_index)

	def create_categories(self, path_to_index):
		object_dict = {}
		with open(path_to_index) as file:
			for line in file:
				split = line.split()
				object_key = split[0]
				category = split[1]
				object_dict[object_key] = category
		self.object_dict_ = object_dict

class SHRECObjectDatabase(MeshDatabase):
	def __init__(self, path_to_index):
		self.create_categories(path_to_index)

	def create_categories(self, path_to_index):
		object_dict = {}
		sorted_keys = []
		with open(path_to_index) as file:
			for skip in xrange(3):
				next(file)

			current_cat = ''
			for line in file:
				split = line.split()
				if len(split) == 3:
					current_cat = split[0]
				elif len(split) == 1:
					object_key = 'M'+split[0]
					object_dict[object_key] = current_cat
					sorted_keys.append(object_key)
		self.object_dict_ = object_dict
		self.sorted_keys_ = sorted_keys

	def sorted_keys(self):
		return self.sorted_keys_
