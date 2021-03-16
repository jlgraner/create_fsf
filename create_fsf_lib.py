
import logging, os
import time, sys
import json, numpy


def write_fsf(output_file, output_dict, overwrite=0):

	logger = logging.getLogger('create_fsf.write_fsf')
	logger.info('<-Starting')

	if os.path.exists(output_file) and overwrite != 1:
		logger.error('fsf file already exists and overwrite is not set!')
		logger.error('output_file: {}'.format(output_file))
		raise RuntimeError('fsf file already exists!')

	#For now, we're just going to write the active lines of code to the fsf file.
	#The lines will not be in the same order as a typical fsf file, but this might
	#not matter. There will also be no comments.
	lines_to_write = []
	for key in output_dict.keys():
		#The feat_files have a unique formatting in the fsf file.
		#Every other line is formatted "set fmri(PARAM) VALUE"
		if key == 'feat_files':
			for num in output_dict['feat_files'].keys():
				lines_to_write.append('set feat_files({}) "{}"'.format(num, output_dict['feat_files'][num]))
		elif key in ['unwarp_dir', 'reghighres_dof', 'con_mode_old', 'con_mode']:
			lines_to_write.append('set fmri({}) {}'.format(key, output_dict[key]))
		else:
			#Strings need double quotes around them in the file
			if type(output_dict[key]) is str:
				lines_to_write.append('set fmri({}) "{}"'.format(key, output_dict[key]))
			else:
				lines_to_write.append('set fmri({}) {}'.format(key, output_dict[key]))

	logger.info('Writing contents to fsf file...')
	with open(output_file, 'w') as fid:
		for line in lines_to_write:
			fid.write('{}\n'.format(line))
			fid.write('\n')
	logger.info('File written: {}'.format(output_file))

	logger.info('<-Finished')



def create_parameter_dict(setup_files, output_dir, tr=3):
	#This function will return a large dictionary of keys:values that will be
	#written into the final output .fsf file.

	logger = logging.getLogger('create_fsf.create_parametric_dict')
	logger.info('<-Starting')

	this_env = os.environ
	fsl_dir = this_env['FSLDIR']

	#setup_files = {
	#			  input_list_file: provided by user; script generation
	#			  param_template_file: provided in code base
	#			  ev_params_file: provided in code base
	#			  ev_matrix_file: provided by user; script generation
	#			  #contrast_params_file: provided in code base#
	#		      contrast_matrix_file: provided by user; script generation
	#			  (ev_ortho_file: provided or variables generated here)
	#			  (group_member_file: provided or variables generated here)
	#			  (contrast_mask_file: provided or variables generated here)
	#			  (contrast_title_file: provided or variables generated here)
	#			}

	#Look for each field in setup_files. If a file was not passed in the field,
	#create a default set of parameters.

	#First, necessary files
	if 'input_list_file' not in setup_files.keys():
		logger.error('No input_list_file included in setup_files!')
		raise RuntimeError('No input_list_file in setup_files')
	if 'param_template_file' not in setup_files.keys():
		logger.error('No param_template_file included in setup_files!')
		raise RuntimeError('No param_template_file in setup_files')
	if 'ev_matrix_file' not in setup_files.keys():
		logger.error('No ev_matrix_file included in setup_files!')
		raise RuntimeError('No ev_matrix_file in setup_files')
	if 'contrast_matrix_file' not in setup_files.keys():
		logger.error('No contrast_matrix_file included in setup_files!')
		raise RuntimeError('No contrast_matrix_file in setup_files')
	if 'ev_params_file' not in setup_files.keys():
		logger.error('No ev_params_file included in setup_files!')
		raise RuntimeError('No ev_params_file in setup_files')

	#Read in list of input files/directories
	logger.info('Reading input list file...')
	input_list = read_input_list(str(setup_files['input_list_file']))
	num_inputs = len(input_list)

	#Read in parameter template file
	logger.info('Reading general parameter template file...')
	general_param_dict = read_param_json(str(setup_files['param_template_file']))

	#Read in the EV matrix, which has one column per EV (2nd dimension) and
	#one row per input file/FEAT_dir (1st dimension)
	logger.info('Reading EV matrix file...')
	ev_matrix = read_matrix(str(setup_files['ev_matrix_file']))
	num_evs = ev_matrix.shape[1]

	#Read in the contrast matrix, which has one column per EV (2nd dimension) and
	#one row per desired contrast
	logger.info('Reading contrast matrix file...')
	contrast_matrix = read_matrix(str(setup_files['contrast_matrix_file']))
	num_contrasts = contrast_matrix.shape[1]

	#Read in EV parameter file
	logger.info('Reading EV parameter file...')
	ev_param_dict = read_param_json(str(setup_files['ev_params_file']))
	#If there is only one top-level entry in the EV parameter dictionary, we'll use
	#the same parameters for every EV.
	if len(ev_param_dict.keys()) == 1:
		use_same_ev_params = 1
	else:
		use_same_ev_params = 0

	# #Read in contrast parameter file
	# logger.info('Reading contrast parameter file...')
	# con_param_dict = read_param_json(str(setup_files['contrast_params_file']))
	# #If there is only one top-level entry in the contrast parameter dictionary, we'll
	# #use the same paremters for every contrast.
	# if len(con_param_dict.keys()) == 1:
	# 	use_same_con_params = 1
	# else:
	# 	use_same_con_params = 0

	#Next, look for files we don't necessarily need
	if 'ev_ortho_file' in setup_files.keys():
		#Read in the file and create the necessary variables
		logger.info('Reading passed EV orthogonalization file...')
		ev_ortho_matrix = read_matrix(str(setup_files['ev_ortho_file']))
	else:
		#Just create the default version of the necessary variables
		#Here, assume none of the EVs should be orthogonalized.
		#The matrix has a second dimension of length num_evs+1 because the
		#fsf file contains orthogonalization to an "EV 0", which is not
		#one of the setup EVs.
		logger.info('Creating default EV orthogonalization matrix...')
		ev_ortho_matrix = numpy.zeros((num_evs, num_evs+1))

	if ('group_member_file' in setup_files.keys()):
		#Read in the file and create a matrix variable.
		#The matrix should have one column and num_input rows.
		logger.info('Reading passed group membership file...')
		group_member_matrix = read_matrix(str(setup_files['group_member_file']))
	else:
		#Create a defaul version putting all the inputs into the same group
		logger.info('Creating default group membership matrix...')
		group_member_matrix = numpy.ones((num_inputs, 1))

	if ('contrast_mask_file' in setup_files.keys()):
		#Read in the file and create a matrix of variable.
		#The matrix should have num_contrasts rows an num_contrasts columns.
		#Elements along the diagonal will be ignored.
		logger.info('Reading passed contrast matrix file...')
		contrast_mask_matrix = read_matrix(str(setup_files['contrast_mask_file']))
	else:
		#Create a default version of all zeroes
		logger.info('Creating default contrast matrix...')
		contrast_mask_matrix = numpy.zeros((num_contrasts, num_contrasts))

	if ('contrast_title_file' in setup_files.keys()):
		#Read in the file and create a list of variables
		#The matrix should have one column and num_contrast rows.
		logger.info('Reading passed contrast titles...')
		contrast_title_list = read_input_list(str(setup_files['contrast_title_file']))
	else:
		#Default values are created elsewhere
		logger.info('No contrast_title_file passed; will use default titles...')
		contrast_title_list = None

	##Create the large parameter dictionary that will be used to create the fsf file
	#Start with the general parameter dictionary and build on it.
	output_dict = general_param_dict

	#Set some values we didn't know before reading in the other files. First check to
	#make sure they aren't specified in a user-provided parameter file.
	logger.info('Setting some parameters...')
	if output_dict['outputdir'] == "None":
		logger.info('outputdir: {}'.format(output_dir))
		output_dict['outputdir'] = str(output_dir)
	if output_dict['tr'] == "None":
		logger.info('tr:{}'.format(tr))
		output_dict['tr'] = float(tr)
	if output_dict['npts'] == "None":
		logger.info('npts:{}'.format(num_inputs))
		output_dict['npts'] = int(num_inputs)
	if output_dict['multiple'] == "None":
		logger.info('multiple: {}'.format(num_inputs))
		output_dict['multiple'] = int(num_inputs)
	if output_dict['evs_orig'] == "None":
		logger.info('evs_orig: {}'.format(num_evs))
		output_dict['evs_orig'] = int(num_evs)
	if output_dict['evs_real'] == "None":
		logger.info('evs_real: {}'.format(num_evs))
		output_dict['evs_real'] = int(num_evs)
	if output_dict['ncon_real'] == "None":
		logger.info('ncon_real: {}'.format(num_contrasts))
		output_dict['ncon_real'] = int(num_contrasts)
	if output_dict['regstandard'] == "None":
		logger.info('regstandard: {}'.format(os.path.join(fsl_dir, 'data', 'standard', 'MNI152_T1_2mm_brain')))
		output_dict['regstandard'] = os.path.join(fsl_dir, 'data', 'standard', 'MNI152_T1_2mm_brain')
	if output_dict['ncopeinputs'] == "None":
		#We actually have to go into one of the passed input directories to find this number
		cope_num = 0
		logger.info('Inspecting input directory for number of lower-level copes...')
		dir_to_test = input_list[0]
		logger.info('Looking in: {}'.format(dir_to_test))
		if os.path.isdir(dir_to_test):
			stats_contents = os.listdir(os.path.join(dir_to_test, 'stats'))
			# print('stats_contents: {}'.format(stats_contents))
			for element in stats_contents:
				if (element[:4] == 'cope') and (element[-7:] == '.nii.gz'):
					cope_num = cope_num + 1
			output_dict['ncopeinputs'] = int(cope_num)
			logger.info('ncopeinputs: {}'.format(cope_num))
		else: #input is a lower-level cope or data file
			logger.info('ncopeinputs: 0')
			output_dict['ncopeinputs'] = 0

	##Add in the information we've created or extracted
	#For now, just include all the lower-level copes in the higher-level analysis
	if int(output_dict['ncopeinputs']) > 0:
		for count in range(cope_num):
			output_dict['copeinput.{}'.format(count+1)] = 1

	#Add the input files or directories
	output_dict['feat_files'] = {}
	for count in range(len(input_list)):
		output_dict['feat_files'][str(count+1)] = input_list[count]

	#Add the EV parameters
	if use_same_ev_params:
		for count in range(num_evs):
			output_dict['evtitle{}'.format(count+1)] = ev_param_dict['evN']['evtitleN']
			output_dict['shape{}'.format(count+1)] = ev_param_dict['evN']['shapeN']
			output_dict['convolve{}'.format(count+1)] = ev_param_dict['evN']['convolveN']
			output_dict['convolve_phase{}'.format(count+1)] = ev_param_dict['evN']['convolve_phaseN']
			output_dict['tempfilt_yn{}'.format(count+1)] = ev_param_dict['evN']['tempfilt_ynN']
			output_dict['deriv_yn{}'.format(count+1)] = ev_param_dict['evN']['deriv_ynN']
			output_dict['custom{}'.format(count+1)] = ev_param_dict['evN']['customN']
	else:
		for count in range(num_evs):
			output_dict['evtitle{}'.format(count+1)] = ev_param_dict['ev{}'.format(count+1)]['evtitleN']
			output_dict['shape{}'.format(count+1)] = ev_param_dict['ev{}'.format(count+1)]['shapeN']
			output_dict['convolve{}'.format(count+1)] = ev_param_dict['ev{}'.format(count+1)]['convolveN']
			output_dict['convolve_phase{}'.format(count+1)] = ev_param_dict['ev{}'.format(count+1)]['convolve_phaseN']
			output_dict['tempfilt_yn{}'.format(count+1)] = ev_param_dict['ev{}'.format(count+1)]['tempfilt_ynN']
			output_dict['deriv_yn{}'.format(count+1)] = ev_param_dict['ev{}'.format(count+1)]['deriv_ynN']
			output_dict['custom{}'.format(count+1)] = ev_param_dict['ev{}'.format(count+1)]['customN']

	#Add in the EV orthogonalizations
	#The indices of orthoX.Y: X starts at 1, Y starts at 0
	for col in range(ev_ortho_matrix.shape[1]):
		output_dict['ortho{}.{}'.format(col+1,0)] = 0
		for row in range(ev_ortho_matrix.shape[0]):
			output_dict['ortho{}.{}'.format(row+1,col+1)] = ev_ortho_matrix[row,col]

	#Add in the EV values for each input
	#The indices of evgX.Y: X = EV, Y = input
	#The ev_matrix must have one row per input and one column per EV
	for col in range(ev_matrix.shape[1]):
		for row in range(ev_matrix.shape[0]):
			output_dict['evg{}.{}'.format(row+1,col+1)] = ev_matrix[row,col]

	#Add in group membership
	for row in range(group_member_matrix.shape[0]):
		output_dict['groupmem.{}'.format(row+1)] = group_member_matrix[row,0]

	#Add in contrast parameters
	# if use_same_con_params:
	if contrast_title_list is not None:
		for count in range(num_contrasts):
			output_dict['conpic_real.{}'.format(count+1)] = 1
			output_dict['conname_real.{}'.format(count+1)] = str(contrast_title_list[count])
	else:
		for count in range(num_contrasts):
			output_dict['conpic_real.{}'.format(count+1)] = 1
			output_dict['conname_real.{}'.format(count+1)] = 'contrast_{}'.format(count+1)

	#Add in contrast matrix
	for col in range(contrast_matrix.shape[1]):
		for row in range(contrast_matrix.shape[0]):
			output_dict['con_real{}.{}'.format(row+1,col+1)] = contrast_matrix[row,col]

	#Add in contrast masking matrix
	for col in range(contrast_mask_matrix.shape[1]):
		for row in range(contrast_mask_matrix.shape[0]):
			if col != row:
				output_dict['conmask{}_{}'.format(row+1,col+1)] = contrast_mask_matrix[row,col]

	logger.info('<-Finished')

	return output_dict


def read_param_json(param_json):
	#param_json: full path/filename of a json file to read

	logger = logging.getLogger('create_fsf.read_param_json')
	logger.info('<-Starting')

	if not os.path.exists(param_json):
		logger.error('Passed parameter json file does not exist: {}'.format(param_json))
		raise RuntimeError('Passed parameter json file does not exist.')

	#Read in parameter file
	logger.info('Reading parameter json file...')
	with open(param_json) as fd:
		param_dict = json.loads(fd.read())

	logger.info('<-Finished')
	#Return the finished parameter dictionary
	return param_dict



def read_input_list(input_list_file):

	logger = logging.getLogger('create_fsf.read_input_list')
	logger.info('<-Starting')

	if not os.path.exists(input_list_file):
		logger.error('Passed input_list_file does not exist: {}'.format(input_list_file))
		raise RuntimeError('Passed input_list_file does not exist.')

	#Read in each line of the input list file and add it to the list
	input_list = []
	logger.info('Reading input list file...')
	with open(input_list_file, 'r') as fd:
		for line in fd:
			input_list.append(line.strip())

	logger.info('<-Finished')
	#Return the finished input list
	return input_list



def read_matrix(matrix_file):

	logger = logging.getLogger('create_fsf.read_matrix')
	logger.info('<-Starting')

	if not os.path.exists(matrix_file):
		logger.error('Passed matrix_file does not exist: {}'.format(matrix_file))
		raise RuntimeError('Passed matrix_file does not exist.')

	#Read the input file in as a numpy array
	output_matrix = numpy.loadtxt(matrix_file)

	logger.info('<-Finished')
	#Return the EV model matrix
	return output_matrix





