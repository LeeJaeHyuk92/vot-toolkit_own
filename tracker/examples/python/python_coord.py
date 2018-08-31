import vot
import sys
sys.path.append('/usr/local/lib')
import os
import glob
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
import tensorflow as tf
from helper.image_proc import cropPadImage
from helper.BoundingBox import BoundingBox, calculate_box

# jaehyuk, check network file
import goturn_net_coord
import numpy as np
import cv2
from helper.config import POLICY
from logger.logger import setup_logger


class bbox_estimator:
    """tracker class"""

    def __init__(self, show_intermediate_output, logger):
        """TODO: to be defined. """
        self.show_intermediate_output = show_intermediate_output
        self.logger = logger

    def init(self, image_curr, region):
        """ initializing the first frame in the video
        """
        left = max(region.x, 0)
        top = max(region.y, 0)
        right = min(region.x + region.width, image.shape[1] - 1)
        bottom = min(region.y + region.height, image.shape[0] - 1)
        bbox_gt = BoundingBox(left, top, right, bottom)
        self.image_prev = image_curr
        self.bbox_prev_tight = bbox_gt
        self.bbox_curr_prior_tight = bbox_gt
        self.DeltaBox = np.array([0., 0.])
        self.lambdaBox = 0.3
        self.prevBoxeffect = 0
        self.occlusion_flag = 0

    def preprocess(self, image):
        """TODO: Docstring for preprocess.

        :arg1: TODO
        :returns: TODO """
        image_out = image
        if image_out.shape != (POLICY['HEIGHT'], POLICY['WIDTH'], POLICY['channels']):
            image_out = cv2.resize(image_out, (POLICY['WIDTH'], POLICY['HEIGHT']), interpolation=cv2.INTER_CUBIC)

        image_out = np.float32(image_out)
        return image_out

    def track(self, image_curr, tracknet, velocity, b_frist, sess):
        """TODO: Docstring for tracker.
        :returns: TODO

        """
        target_pad, _, _,  _ = cropPadImage(self.bbox_prev_tight, self.image_prev)
        cur_search_region, search_location, edge_spacing_x, edge_spacing_y = cropPadImage(self.bbox_curr_prior_tight, image_curr)

        # image, BGR(training type)
        cur_search_region_resize = self.preprocess(cur_search_region)
        target_pad_resize = self.preprocess(target_pad)
        
        # jaehyuk, check hanning windows
        hann_1d = np.expand_dims(np.hanning(227), axis=0)
        hann_2d = np.transpose(hann_1d) * hann_1d
        hann_2d = np.expand_dims(hann_2d, axis=2)
        target_pad_resize = target_pad_resize * hann_2d

        cur_search_region_expdim = np.expand_dims(cur_search_region_resize, axis=0)
        target_pad_expdim = np.expand_dims(target_pad_resize, axis=0)

        re_fc4_image, fc4_adj = sess.run([tracknet.re_fc4_image, tracknet.fc4_adj],
                                         feed_dict={tracknet.image: cur_search_region_expdim,
                                                    tracknet.target: target_pad_expdim})
        bbox_estimate, object_bool, objectness = calculate_box(re_fc4_image, fc4_adj)
        print('objectness_s is: ', objectness)

        ########### original method ############
        # this box is NMS result, TODO, all bbox check

        if not len(bbox_estimate) == 0:
            bbox_estimate = BoundingBox(bbox_estimate[0][0], bbox_estimate[0][1], bbox_estimate[0][2], bbox_estimate[0][3])

            # Inplace correction of bounding box
            bbox_estimate.unscale(cur_search_region)
            bbox_estimate.uncenter(image_curr, search_location, edge_spacing_x, edge_spacing_y)

            # jaehyuk, check first vs adj
            # self.image_prev = image_curr
            # self.bbox_prev_tight = bbox_estimate
            self.bbox_curr_prior_tight = bbox_estimate
        else:
            # self.image_prev = self.image_prev
            # self.bbox_prev_tight = self.bbox_prev_tight
            self.bbox_curr_prior_tight =self.bbox_curr_prior_tight
            bbox_estimate = self.bbox_curr_prior_tight

        ########### original method ############


        ############ trick method ############

        # if object_bool:
        # # if not len(bbox_estimate) == 0:
        #     # current_box_wh = np.array([(bbox_estimate.[0][2] - bbox_estimate.[0][0]), (bbox_estimate.[0][3] - bbox_estimate.[0][1])], dtype=np.float32)
        #     # prev_box_wh = np.array([5., 5.], dtype=np.float32)
        #
        #     bbox_estimate = BoundingBox(bbox_estimate[0][0], bbox_estimate[0][1], bbox_estimate[0][2], bbox_estimate[0][3])
        #
        #     # relative distance from center point [5. 5.]
        #     relative_current_box = np.array([(bbox_estimate.x2 + bbox_estimate.x1) / 2,
        #                             (bbox_estimate.y2 + bbox_estimate.y1) / 2],
        #                            dtype=np.float32)
        #     relative_distance = np.linalg.norm(relative_current_box - np.array([5., 5.]))
        #
        #     # Inplace correction of bounding box
        #     bbox_estimate.unscale(cur_search_region)
        #     bbox_estimate.uncenter(image_curr, search_location, edge_spacing_x, edge_spacing_y)
        #
        #     # image's width height , center point
        #     current_box = np.array([(bbox_estimate.x2 + bbox_estimate.x1) / 2, (bbox_estimate.y2 + bbox_estimate.y1) / 2], dtype=np.float32)
        #     prev_box = np.array([(self.bbox_curr_prior_tight.x2 + self.bbox_curr_prior_tight.x1) / 2, (self.bbox_curr_prior_tight.y2 + self.bbox_curr_prior_tight.y1) / 2],
        #                         dtype=np.float32)
        #
        #     if relative_distance < 2:
        #         self.DeltaBox = self.lambdaBox * (current_box - prev_box) + (1 - self.lambdaBox) * self.DeltaBox
        #
        #
        #         self.image_prev = image_curr
        #         self.bbox_prev_tight = bbox_estimate
        #         self.bbox_curr_prior_tight = bbox_estimate
        #         print(self.DeltaBox)
        #     else:
        #         # under prev img, box block is no update
        #         self.image_prev = self.image_prev
        #         self.bbox_prev_tight = self.bbox_prev_tight
        #         # self.bbox_curr_prior_tight = self.bbox_prev_tight
        #         self.bbox_curr_prior_tight = BoundingBox(self.bbox_curr_prior_tight.x1 + self.DeltaBox[0],
        #                                                  self.bbox_curr_prior_tight.y1 + self.DeltaBox[1],
        #                                                  self.bbox_curr_prior_tight.x2 + self.DeltaBox[0],
        #                                                  self.bbox_curr_prior_tight.y2 + self.DeltaBox[1])
        #         bbox_estimate = self.bbox_curr_prior_tight
        #         print('distance is {:>3}'.format(relative_distance))
        #         print(self.DeltaBox)
        # else:
        #     # under prev img, box block is no update
        #     self.image_prev = self.image_prev
        #     self.bbox_prev_tight = self.bbox_prev_tight
        #     # self.bbox_curr_prior_tight = self.bbox_prev_tight
        #     self.bbox_curr_prior_tight = BoundingBox(self.bbox_curr_prior_tight.x1 + self.DeltaBox[0],
        #                                              self.bbox_curr_prior_tight.y1 + self.DeltaBox[1],
        #                                              self.bbox_curr_prior_tight.x2 + self.DeltaBox[0],
        #                                              self.bbox_curr_prior_tight.y2 + self.DeltaBox[1])
        #     bbox_estimate = self.bbox_curr_prior_tight
        #     print('occlusion is detected')
        #     print(self.DeltaBox)
        #
        # ############ trick method ############

        left_x = bbox_estimate.x1
        left_y = bbox_estimate.y1
        width = bbox_estimate.x2 - bbox_estimate.x1
        height = bbox_estimate.y2 - bbox_estimate.y1
        return vot.Rectangle(left_x, left_y, width, height)
        # return bbox_estimate

handle = vot.VOT("rectangle")
selection = handle.region()
BATCH_SIZE = 1
logger = setup_logger(logfile=None)
# ckpt = '/datahdd/workdir/jaehyuk/code/experiment/vgg19/grid13_box1_vgg19_alltraining/checkpoints/checkpoint.ckpt-277261'
# ckpt = '/datahdd/workdir/jaehyuk/checkpoints/VIDtracker/180712_adj/checkpoint.ckpt-560836'
# ckpt = '/home/jaehyuk/code/experiment/VIDonline/checkpoints/checkpoint.ckpt-37081'
# ckpt = "/home/jaehyuk/code/github/vot-toolkit/tracker/examples/python/checkpoints/checkpoint.ckpt-111241"
ckpt_dir = "/home/jaehyuk/code/github/vot-toolkit/tracker/examples/python/checkpoints"
# ckpt_dir = "./checkpoints"
ckpt = None
DET_ckpt = '/home/jaehyuk/code/github/vot-toolkit/tracker/examples/python/checkpoints_online/checkpoint.ckpt-303337'


imagefile = handle.frame()
if not imagefile:
    sys.exit(0)
    
bbox_estim = bbox_estimator(False, logger)
# jaehyuk, check network file
tracknet = goturn_net_coord.TRACKNET(BATCH_SIZE, train=False)
tracknet.build()


sess = tf.Session()
init = tf.global_variables_initializer()
init_local = tf.local_variables_initializer()
sess.run(init)
sess.run(init_local)

coord = tf.train.Coordinator()
# start the threads
tf.train.start_queue_runners(sess=sess, coord=coord)

### ckpt
if not os.path.exists(ckpt_dir):
    os.makedirs(ckpt_dir)

# jaehyuk, check checkpoint, descend
all_ckpt_meta = glob.glob(os.path.join(ckpt_dir, '*.meta'))
num = []
for ckpt_meta in all_ckpt_meta:
    num.append(int(ckpt_meta.split('-')[2].split('.')[0]))
max_num = max(num)
ckpt = os.path.join(ckpt_dir, 'checkpoint.ckpt-' + str(max_num))

if ckpt:
    saver = tf.train.Saver()
    saver.restore(sess, ckpt)
    logger.info(str(ckpt) + " is restored")
else:
    # ckpt = tf.train.get_checkpoint_state(ckpt_dir)

    saver = tf.train.Saver()
    saver.restore(sess, ckpt)
    logger.info("model is restored using " + str(ckpt))


image = cv2.imread(imagefile)
bbox_estim.init(image, selection)
velocity = 0
b_frist = True
while True:
    imagefile = handle.frame()
    if not imagefile:
        break
    image = cv2.imread(imagefile)
    bbox = bbox_estim.track(image, tracknet, velocity, b_frist, sess)
    handle.report(bbox)
    b_frist = False

