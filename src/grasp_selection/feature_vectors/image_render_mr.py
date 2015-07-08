import csv
import shutil
import math
import argparse

import maya.standalone
import maya.cmds as cmd
import maya.mel as mel
maya.standalone.initialize(name='python')
mel.eval('source "renderLayerBuiltinPreset.mel"')

def loadMentalRayPlugin():
	name = 'Mayatomr'
	if not cmd.pluginInfo(name, q=True, loaded=True):
		cmd.loadPlugin(name)
		cmd.pluginInfo(name, edit=True, autoload=True)
	cmd.setAttr('defaultRenderGlobals.currentRenderer', 'mentalRay', type='string')
loadMentalRayPlugin()

cmd.setAttr("defaultRenderGlobals.imageFormat", 32)

cmd.setAttr("miDefaultFramebuffer.interpolateSamples", 0)

parser = argparse.ArgumentParser()

parser.add_argument("mesh_file",
					help="the path to the mesh file")
parser.add_argument("dest_dir",
					help="the destination directory to store the images")
parser.add_argument("--name", default="unnamed",
					help="the name of the image")
parser.add_argument("--min_dist", type=float, default=0.3,
					help="the minimun distance from the object to capture images")
parser.add_argument("--max_dist", type=float, default=0.5,
					help="the maximum distance from the object to capture images")
parser.add_argument("--num_radial", type=int, default=2,
					help="the number of radial steps")
parser.add_argument("--num_lat", type=int, default=3,
					help="the number of latitudinal steps")
parser.add_argument("--num_long", type=int, default=3,
					help="the number of longitudinal steps")
parser.add_argument("--min_range", type=float, default=0,
					help="the minimum range of the depth image")
parser.add_argument("--max_range", type=float, default=1,
					help="the maximum range of the depth image")
parser.add_argument("-m", "--mesh", action="store_true",
                    help="save mesh images")
parser.add_argument("-s", "--segmask", action="store_true",
                    help="save segmentation mask images")
parser.add_argument("-d", "--depth", action="store_true",
                    help="save depth images")
parser.add_argument("-nt", "--no_table", action="store_true",
                    help="don't render table under object")

args = parser.parse_args()

mesh_file = args.mesh_file
dest_dir = args.dest_dir
image_name = args.name
min_dist = args.min_dist
max_dist = args.max_dist
num_radial = args.num_radial
num_lat = args.num_lat
num_long = args.num_long
min_range = args.min_range
max_range = args.max_range

mesh = args.mesh
segmask = args.segmask
depth = args.depth
no_table = args.no_table

file_type = "png"

obj_name = "OBJECT"
plane_name = "PLANE"

center_of_interest = [0,0,0]

def add_depth_layer():
	depth_layer_name = "DEPTH_LAYER"

	if no_table:
		cmd.select(obj_name+":Mesh")
	else:
		cmd.select(obj_name+":Mesh", plane_name, r=True)
	cmd.createRenderLayer(name=depth_layer_name)
	mel.eval("renderLayerBuiltinPreset linearDepth DEPTH_LAYER")
	cmd.disconnectAttr("samplerInfo1.cameraNearClipPlane", "setRange1.oldMinX")
	cmd.disconnectAttr("samplerInfo1.cameraFarClipPlane", "setRange1.oldMaxX")
	cmd.setAttr("setRange1.minX", 0)
	cmd.setAttr("setRange1.maxX", 1)
	cmd.setAttr("setRange1.oldMinX", min_range)
	cmd.setAttr("setRange1.oldMaxX", max_range)

def add_object_segmentation():
	create_mask_for_object_with_color(obj_name+":Mesh", [1, 1, 1])
	create_mask_for_object_with_color(plane_name, [1, 0, 0])

def create_scene_with_mesh(mesh_file):
	global center_of_interest

	cmd.file(f=True, new=True)

	if not no_table:
		cmd.nurbsPlane(name=plane_name, p=(0,0,0), ax=(0,1,0), w=100, lr=1, d=3, u=1, v=1, ch=1)

	cmd.file(mesh_file, i=True, ns=obj_name)
	cmd.select(obj_name+":Mesh", r=True)
	bounding_box = cmd.polyEvaluate(b=True)
	cmd.move(-bounding_box[1][0], y=True)
	object_height = bounding_box[1][1] - bounding_box[1][0]

	center_of_interest = [0, object_height/2, 0]

	cmd.setAttr("defaultRenderGlobals.imageFormat", 32)

def create_mask_for_object_with_color(obj_name, color):
	mask_name = obj_name+"_MASK"
	group_name = obj_name+"_GROUP"

	cmd.shadingNode("surfaceShader", name=mask_name, asShader=True)
	cmd.setAttr(mask_name+".outColor", color[0], color[1], color[2], type="double3")

	cmd.sets(name=group_name, renderable=True, empty=True)
	cmd.surfaceShaderList(mask_name, add=group_name)
	cmd.sets(obj_name, e=True, forceElement=group_name)

def save_image_with_camera_pos(csv_writer, image_name, file_ext, camera_pos, camera_interest_pos):
	camera_name, camera_shape = cmd.camera(p=camera_pos, wci=camera_interest_pos)
	cmd.setAttr(camera_shape+".renderable", 1)
	focal_length = cmd.camera(camera_shape, q=True, fl=True)

	inches_to_mm = 25.4
	app_horiz = cmd.camera(camera_shape, q=True, hfa=True) * inches_to_mm
	app_vert = cmd.camera(camera_shape, q=True, vfa=True) * inches_to_mm
	pixel_width = cmd.getAttr("defaultResolution.width")
	pixel_height = cmd.getAttr("defaultResolution.height")

	focal_length_x_pixel = pixel_width * focal_length / app_horiz
	focal_length_y_pixel = pixel_height * focal_length / app_vert

	# print cmd.camera(camera_shape, q=True, fs=True)
	# print focal_length
	# print app_horiz, app_vert
	# print focal_length_x_pixel, focal_length_y_pixel

	image_file = image_name+"."+file_ext
	image_src = cmd.render(camera_shape)
	image_dest = dest_dir+"/"+image_file
	shutil.move(image_src, image_dest)

	save_camera_data_to_writer(csv_writer, image_name, camera_pos, camera_interest_pos, focal_length)

def save_camera_data_to_writer(csv_writer, image_file, camera_pos, camera_interest_pos, focal_length):
	csv_writer.writerow(camera_pos + camera_interest_pos + [focal_length, image_file])

def create_images_for_scene(csv_writer, obj_name, min_dist, max_dist, num_radial, num_lat, num_long):
	radius = min_dist
	radial_increment = 0 if num_radial == 1 else (max_dist - min_dist) / (num_radial - 1)

	for r in range(0, num_radial):
		phi_increment = math.pi / 2 / (num_lat + 1)
		phi = phi_increment
		for lat in range(0, num_lat):
			theta = 0
			theta_increment = 2 * math.pi / num_long
			for lon in range(0, num_long):
				camera_pos = [radius*math.sin(phi)*math.cos(theta), radius*math.cos(phi), radius*math.sin(phi)*math.sin(theta)]
				image_name = obj_name+"_"+str(r)+"_"+str(lat)+"_"+str(lon)
				save_image_with_camera_pos(csv_writer, image_name, file_type, camera_pos, center_of_interest)
				theta += theta_increment
			phi += phi_increment
		radius += radial_increment

with open(dest_dir+"/"+'camera_table.csv', 'w') as csvfile:
	csv_writer = csv.writer(csvfile)
	csv_writer.writerow(["camera_x", "camera_y", "camera_z", "interest_x", "interest_y", "interest_z", "focal_length", "image_name"])

	if mesh:
		create_scene_with_mesh(mesh_file)
		create_images_for_scene(csv_writer, image_name+"|mesh", min_dist, max_dist, num_radial, num_lat, num_long)

	if segmask:
		create_scene_with_mesh(mesh_file)
		add_object_segmentation()
		create_images_for_scene(csv_writer, image_name+"|segmask", min_dist, max_dist, num_radial, num_lat, num_long)

	if depth:
		create_scene_with_mesh(mesh_file)
		add_depth_layer()
		create_images_for_scene(csv_writer, image_name+"|depth", min_dist, max_dist, num_radial, num_lat, num_long)


# def create_robot_pose_matrix(camera_pos, camera_interest_pos):
# 	z_axis = numpy.subtract(camera_interest_pos, camera_pos)
# 	z = numpy.linalg.norm(z_axis)
# 	x = numpy.linalg.norm(numpy.cross([0,1,0], z))
# 	y = numpy.linalg.norm(numpy.cross(z, x))
