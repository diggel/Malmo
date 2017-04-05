from configuration import config as cfg
from minecraft_graph_locomotion import MinecraftGraphLocomotion
from minecraft_projection_mixin import MinecraftProjectionMixin


class MinecraftVision(MinecraftGraphLocomotion, MinecraftProjectionMixin):

    logger = None

    # specs for vision /fovea
    # image width and height define the part of the world that can be viewed
    # ie. they provide the proportions of the projection /image plane in the world
    im_width = 128
    im_height = 64
    # camera values define width and height of the normalized device /camera /viewport
    cam_width = 1.
    cam_height = 1.
    # focal length defines the distance between the image plane and the projective point /fovea
    # ( focal length > 0 means zooming in, < 0 means zooming out;
    #   small values distort the image, in particular if objects are close )
    focal_length = 0.5
    # the maximal distance for raytracing -- the value was determined by manually trying several values
    max_dist = 64

    # Six parameters determine the agent's visual input: fov_x and fov_y, res_x and res_y, len_x and len_y.
    # They describe the fovea position, the zoom level aka resolution level, and the number of receptors respectively.
    # The first four variables are local, the other two are fields. Note: a rectangular receptor field is assumed.
    len_x = 16
    len_y = 16

    # tiling used for splitting visual field into sections
    tiling_x = 7
    tiling_y = 3

    # cf. autoencoders require similar activation ( up to noise ) for three consecutive steps
    num_steps_to_keep_vision_stable = 3

    def __init__(self, world, uid=None, **data):

        super().__init__(world, uid, **data)

        # don't use fov_act_00_00 because it complicates debug plots
        self.fovea_actuator = "fov_act__01_03"

        # add datasources for fovea sensors aka fov__*_*
        for i in range(self.len_x):
            for j in range(self.len_y):
                name = "fov__%02d_%02d" % (i, j)
                self.datasources[name] = 0.

        # add datasources for fovea position sensors aka fov_pos__*_*
        for x in range(self.tiling_x):
            for y in range(self.tiling_y):
                name = "fov_pos__%02d_%02d" % (y, x)
                self.datasources[name] = 0.

        # add fovea actuators to datatargets, datatarget_feedback, datatarget_history, and actions
        for x in range(self.tiling_x):
            for y in range(self.tiling_y):
                name = "fov_act__%02d_%02d" % (y, x)
                self.datatargets[name] = 0.
                self.datatarget_feedback[name] = 0.
                self.datatarget_history[name] = 0.
                self.actions.append(name)

        self.simulated_vision = False
        if 'simulate_vision' in cfg['minecraft']:
            self.simulated_vision = True
            self.simulated_vision_datafile = cfg['minecraft']['simulate_vision']
            self.logger.info("Setting up minecraft_graph_locomotor to simulate vision from data file %s", self.simulated_vision_datafile)

            import os
            import csv
            self.simulated_vision_data = None
            self.simulated_vision_datareader = csv.reader(open(self.simulated_vision_datafile))
            if os.path.getsize(self.simulated_vision_datafile) < (500 * 1024 * 1024):
                self.simulated_vision_data = [[float(datapoint) for datapoint in sample] for sample in self.simulated_vision_datareader]
                self.simulated_data_entry_index = 0
                self.simulated_data_entry_max = len(self.simulated_vision_data) - 1

        if 'record_vision' in cfg['minecraft']:
            self.record_file = open(cfg['minecraft']['record_vision'], 'a')

        self.visual_field = {}

    def update_data_sources_and_targets(self):
        """called on every world calculation step to advance the life of the agent"""

        # first thing when spock initialization is done, determine current loco node
        if self.simulated_vision:
            self.simulate_visual_input(self.len_x, self.len_y)

        else:
            super().update_data_sources_and_targets()

            if not self.waiting_for_spock:
                # handle fovea actuators and sensors: action feedback, relay to sensors, default actuator
                active_fovea_actuator = None
                for x in range(self.tiling_x):
                    for y in range(self.tiling_y):
                        actuator_name = "fov_act__%02d_%02d" % (y, x)
                        sensor_name = "fov_pos__%02d_%02d" % (y, x)
                        # relay activation of fovea actuators to fovea sensor nodes
                        self.datasources[sensor_name] = self.datatargets[actuator_name]
                        # provide action feedback for fovea actuator nodes
                        if self.datatargets[actuator_name] > 0.:
                            self.datatarget_feedback[actuator_name] = 1.
                            active_fovea_actuator = actuator_name

                # if there's no active_fovea_actuator use the last fovea position as default
                if active_fovea_actuator is None:
                    active_fovea_actuator = self.fovea_actuator
                    self.datasources[active_fovea_actuator.replace("act", "pos")] = 1.
                    self.datatarget_feedback[active_fovea_actuator] = 1.

                # determine if fovea position changed
                fovea_position_changed = self.fovea_actuator != active_fovea_actuator
                # store the currently active fovea actuator node name for the next round
                self.fovea_actuator = active_fovea_actuator

                # change pitch and yaw every x world steps to increase sensory variation
                # < ensures some stability to enable learning in the autoencoder
                if self.world.current_step % self.num_steps_to_keep_vision_stable == 0:
                    # for patches pitch = 10 and yaw = random.randint(-10,10) were used
                    # for visual field pitch = randint(0, 30) and yaw = randint(1, 360) were used
                    self.spockplugin.clientinfo.position['pitch'] = 10
                    self.spockplugin.clientinfo.position['yaw'] = 180  # random.randint(1, 360)
                    self.datatargets['pitch'] = self.spockplugin.clientinfo.position['pitch']
                    self.datatargets['yaw'] = self.spockplugin.clientinfo.position['yaw']
                    # Note: datatargets carry spikes not continuous signals, ie. pitch & yaw will be 0 in the next step
                    self.datatarget_feedback['pitch'] = 1.0
                    self.datatarget_feedback['yaw'] = 1.0

                # TODO: recompute visual input only if self.world.current_step % self.num_steps_to_keep_vision_stable == 0
                # else re-write previous sensor values to datasources

                # sample all the time
                loco_label = self.current_loco_node['name']  # because python uses call-by-object
                # get indices of section currently viewed, i.e. the respective active fovea actuator
                y_sec, x_sec = [int(val) for val in self.fovea_actuator.split('_')[-2:]]
                # translate x_sec, y_sec, and z_oom to fov_x, fov_y, res_x, res_y
                fov_x, fov_y, res_x, res_y = self.translate_xyz_to_vision_params(x_sec, y_sec, 1)  # z_oom = 1
                self.get_visual_input(fov_x, fov_y, res_x, res_y, self.len_x, self.len_y, loco_label)

                self.collect_visual_data()
                if cfg['minecraft'].get('debug_vision') and fovea_position_changed:
                    self.plot_visual_field()

    def locomote(self, target_loco_node_uid):

        if cfg['minecraft'].get('debug_vision') and hasattr(self, 'visual_field'):
            self.visual_field = {}

        super().locomote(target_loco_node_uid)

    def translate_xyz_to_vision_params(self, x_sec, y_sec, z_oom):
        """
        Visual input can be retrieved given a fovea position in terms of (fov_x, fov_y),
        a resolution for each dimension (res_x, res_y), and a excerpt or patch of the
        complete visual field (len_x, len_y). This world adapter offers three actuators:
        x_sec, y_sec, and z_oom. These need to be translated to the parameters which
        determine where to compute the visual input. This translation happens here.
        """
        # add a buffer to self.tiling_x/y because the rays peak out of their
        # assigned image plane sections #TODO validate the magic number 2
        fov_x = (1.0 / (self.tiling_x + 2)) * x_sec
        fov_y = (1.0 / (self.tiling_y + 2)) * y_sec

        res_x = (self.len_x * (4 ** z_oom)) / self.im_width
        res_y = (self.len_y * (2 ** z_oom)) / self.im_height

        # Note: for now, len_x and len_y are stable and don't change dynamically.
        # Hence there's no translation regarding their values here.

        return fov_x, fov_y, res_x, res_y

    def get_visual_input(self, fov_x, fov_y, res_x, res_y, len_x, len_y, label):
        """
        Spans an image plane ( of size ... ), selects a patch on that image plane
        starting from (fov_x, fov_y) and of size (len_x, len_y) and raytraces
        in the Minecraft block world to fill that patch with block type values
        of a 2D perspective projection.

        Order of traversal: left to right, top to bottom ( before rotation );
        that is fov_00_00 gets the top left pixel.
        """
        if res_x == 0.0 or res_y == 0.0 or len_x == 0.0 or len_y == 0.0:
            return

        # get agent position
        pos_x = self.spockplugin.clientinfo.position['x']
        pos_y = self.spockplugin.clientinfo.position['y'] + 0.620  # add some stance to y pos ( which is ground + 1 )
        pos_z = self.spockplugin.clientinfo.position['z']

        # get yaw and pitch ( in degrees )
        yaw = self.spockplugin.clientinfo.position['yaw']
        pitch = self.spockplugin.clientinfo.position['pitch']

        # compute ticks per dimension
        tick_w = self.cam_width / self.im_width / res_x
        tick_h = self.cam_height / self.im_height / res_y

        # span image plane
        # the horizontal plane is split half-half, the vertical plane is shifted upwards
        h_line = [i for i in self.frange(pos_x - 0.5 * self.cam_width, pos_x + 0.5 * self.cam_width, tick_w)]
        v_line = [i for i in self.frange(pos_y - 0.05 * self.cam_height, pos_y + 0.95 * self.cam_height, tick_h)]

        # scale up fov_x, fov_y - which is originally in the domain [0,1]
        # fov_x = int(round(fov_x * (self.im_width * res_x - len_x)))
        # fov_y = int(round(fov_y * (self.im_height * res_y - len_y)))
        fov_x = int(round(fov_x * len(h_line)))
        fov_y = int(round(fov_y * len(v_line)))

        x0, y0, z0 = pos_x, pos_y, pos_z  # agent's position aka projective point
        zi = z0 + self.focal_length

        v_line.reverse()  # inline

        # do raytracing to compute the resp. block type values of a 2D perspective projection
        sensor_values = []
        for i in range(len_x):
            for j in range(len_y):
                try:
                    block_type, distance = self.project(h_line[fov_x + j], v_line[fov_y + i], zi, x0, y0, z0, yaw, pitch)
                except IndexError:
                    block_type, distance = -1, -1
                    self.logger.warning("IndexError at (%d,%d)" % (fov_x + j, fov_y + i))
                sensor_values.append(block_type)

        # homogeneous_patch = False
        # if sensor_values[1:] == sensor_values[:-1]:  # if all sensor values are the same, ignore the sample ie. write zeros
        #     homogeneous_patch = True
        #     norm_sensor_values = [0.0] * len_x * len_y

        # preprocess sensor values
        # # BINARIZE
        # # convert block types into binary values: map air and emptiness to black (0), everything else to white (1)
        # sensor_values_ = [0.0 if v <= 0 else 1.0 for v in sensor_values]
        # GRAY-SCALE VALUES
        from .structs import block_colors
        # fetch RGB value, convert it to gray-scale value in YUV space
        sensor_values_ = []
        for bt in sensor_values:
            red, green, blue = block_colors[str(bt)]
            red, green, blue = red / 255., green / 255., blue / 255.  # normalize to [0, 1]
            # RGB to Y transform
            y = 0.299 * red + 0.587 * green + 0.114 * blue  # digital CCIR601
            sensor_values_.append(y)

        # normalize the sensor values
        norm_sensor_values = self.normalize_sensor_values(sensor_values_)

        # write new sensor values to datasources
        self.write_visual_input_to_datasources(norm_sensor_values, len_x, len_y)

        if 'record_vision' in cfg['minecraft']:
            # do *not* record homogeneous and replayed patches
            if not self.simulated_vision:  # if not homogeneous_patch and not self.simulated_vision:
                if label == self.current_loco_node['name']:
                    data = "{0}".format(",".join(str(b) for b in sensor_values))
                    self.record_file.write("%s,%s,%d,%d,%d,%d,%.3f,%.3f,%d,%d\n" %
                                           (data, label, pitch, yaw, fov_x, fov_y, res_x, res_y, len_x, len_y))
                else:
                    self.logger.warning('potentially corrupt data were ignored')

    def simulate_visual_input(self, len_x, len_y):
        """
        Every <self.num_steps_to_keep_vision_stable> steps read the next line
        from the vision file and fill its values into fov__*_* datasources.
        """
        if self.world.current_step % self.num_steps_to_keep_vision_stable == 0:
            line = None
            if self.simulated_vision_data is None:
                line = next(self.simulated_vision_datareader, None)
                if line is None:
                    self.logger.info("Simulating vision from data file, starting over...")
                    import csv
                    self.simulated_vision_datareader = csv.reader(open(self.simulated_vision_datafile))
                    line = next(self.simulated_vision_datareader)
                line = [float(entry) for entry in line]
            else:
                self.simulated_data_entry_index += 1
                if self.simulated_data_entry_index > self.simulated_data_entry_max:
                    self.logger.info("Simulating vision from memory, starting over, %s entries.", self.simulated_data_entry_max + 1)
                    self.simulated_data_entry_index = 0
                line = self.simulated_vision_data[self.simulated_data_entry_index]
            self.write_visual_input_to_datasources(line, len_x, len_y)

    def write_visual_input_to_datasources(self, sensor_values, len_x, len_y):
        """
        Write computed fovea sensor values to the respective datasources fov__*_*.
        """
        for x in range(len_x):
            for y in range(len_y):
                name = 'fov__%02d_%02d' % (x, y)
                self.datasources[name] = sensor_values[(len_y * x) + y]

    def normalize_sensor_values(self, patch):
        """
        Normalize sensor values to zero mean and 3 standard deviation.
        TODO: make doc correct and precise.
        """
        # normalize block type values
        # subtract the sample mean from each of its pixels
        mean = float(sum(patch)) / len(patch)
        patch_avg = [x - mean for x in patch]  # TODO: throws error in ipython - why not here !?

        # truncate to +/- 3 standard deviations and scale to -1 and +1

        var = [x ** 2.0 for x in patch_avg]
        std = (sum(var) / len(var)) ** 0.5  # ASSUMPTION: all values of x are equally likely
        pstd = 3.0 * std
        # if block types are all the same number, eg. -1, std will be 0, therefore
        if pstd == 0.0:
            patch_std = [0.0 for x in patch_avg]
        else:
            patch_std = [max(min(x, pstd), -pstd) / pstd for x in patch_avg]

        # scale from [-1,+1] to [0.1,0.9] and write values to sensors
        patch_resc = [(1.0 + x) * 0.4 + 0.1 for x in patch_std]
        return patch_resc

    def collect_visual_data(self):
        """ Collect the visual data for the current fovea position
        Resets the data if fovea-position is at 0/0
        """
        # if it's the top-left fovea actuator, reset the visual field by emptying the buffer
        # ( background: this method only works with scanning for now; scanning starts at
        #   fov_act__00_00; so if that's the current fovea actuator, it's time for a new plot )
        if self.fovea_actuator == 'fov_act__00_00':
            self.visual_field = {}

        # if values for this position in the grid exist already, return
        if self.fovea_actuator in self.visual_field:
            return

        keys = sorted(list(self.datasources.keys()))
        activations = [self.datasources[key] for key in keys if key.startswith('fov__')]

        self.visual_field[self.fovea_actuator] = activations

    def plot_visual_field(self):
        """
        Visualize the entire visual field of the agent at a given position.

        Works only in combination with scanning for now because the plot is
        generated only if all tiling_x times tiling_y patches are filled with
        values starting from fov_act__00_00.

        TODO: refactor code such that a plot is always generated right before
        locomotion with the patches that happened to have been sampled.
        """

        from micropsi_core.nodenet import vizapi
        import os
        import numpy as np

        # once every tile has been filled with content, plot the actual image
        if len(set(self.visual_field.keys())) == (self.tiling_x * self.tiling_y):

            i = 0
            while True:

                filename_png = os.path.join(
                    os.path.dirname(os.path.realpath(__file__)),
                    "%s_%d.png" % (self.current_loco_node['name'], i))
                # ??
                if not os.path.exists(filename_png):
                    break
                i += 1

            # sort keys to get them into the correct order, cf. names are given
            # left to right, top to bottom
            sorted_keys = list(self.visual_field.keys())
            sorted_keys.sort()

            # collect values
            A = np.zeros((len(sorted_keys), len([k for k in self.datasources.keys() if k.startswith('fov__')])))
            for i, key in enumerate(sorted_keys):
                A[i, :] = np.array(self.visual_field[key])

            (r, c) = A.shape
            image = vizapi.NodenetPlot(plotsize=(7, 3))
            A = A.reshape(3, 7, int(np.sqrt(c)), int(np.sqrt(c)))
            image.add_4d_matrix_plot(A, hspace=0, wspace=0, vmin=A.min(), vmax=A.max())

            image.save_to_file(filename_png, transparent=True, dpi=300)

    def frange(self, start, end, step):
        """
        Range for floats.
        """
        while start < end:
            yield start
            start += step
