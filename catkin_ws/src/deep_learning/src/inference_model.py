#!/usr/bin/env python
import os, sys, argparse, errno, yaml, time, datetime
import rospy, rospkg
import torch, torchvision, cv2
import numpy as np
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import CompressedImage, Image
from jetcam_ros.utils import bgr8_to_jpeg

class Inference_Model_Node(object):
    def __init__(self):
        self.package = "deep_learning"
        self.node_name = rospy.get_name()
        self.veh_name = self.node_name.split("/")[1]
        rospy.loginfo("{}  Initializing inference_model.py......".format(self.node_name))

        # set/get ros param
        self.model_name  = rospy.get_param("~inference_model/model_pth","best.pth")
        self.use_cuda  = rospy.get_param("~inference_model/use_cuda",True)

        # read information
        self.recording = self.read_param_from_file(file_name="recording.yaml", file_folder="model")

        # configure model
        self.labels = list(self.recording[self.model_name]["labels"].keys())
        self.kind_of_classifier = len(self.labels)
        self.model_struct = self.recording[self.model_name]["train"]["model"]
        #self.neural_network(model=self.model_struct, param_pretrained=False, kind_of_classifier=self.kind_of_classifier) # configure: self.model 
        #self.cuda(use=self.use_cuda) # configure: self.device, self.model

        # configure parameter with processing image
        self.process_img_mean  = 255.0 * np.array([0.485, 0.456, 0.406])
        self.process_img_stdev = 255.0 * np.array([0.229, 0.224, 0.225])
        self.process_img_normalize = torchvision.transforms.Normalize(self.process_img_mean, self.process_img_stdev)

        # CV_bridge
        self.bridge = CvBridge()

        # configure subscriber
        self.sub_msg = rospy.Subscriber("~image/raw",Image,self.convert_image_to_cv2,queue_size=1)

    def neural_network(self, model="alexnet", param_pretrained=False, kind_of_classifier=2):
        # reference : https://pytorch.org/docs/stable/torchvision/models.html
        model_list = [
                      "resnet18", "alexnet", "squeezenet", "vgg16", 
                      "densenet", "inception", "googlenet", "shufflenet", 
                      "mobilenet", "resnet34", "wide_resnet50_2", "mnasnet" 
                     ]

        if model in model_list:
            rospy.loginfo("This model use [{}]. Need some time to load model...".format(model))
            start_time = rospy.get_time()
            if model == "resnet18":
                self.model = torchvision.models.resnet18(pretrained=param_pretrained)
                self.model.fc = torch.nn.Linear(512,kind_of_classifier)
            elif model == "alexnet":
                self.model = torchvision.models.alexnet(pretrained=param_pretrained)
                self.model.classifier[-1] = torch.nn.Linear(self.model.classifier[-1].in_features, int(kind_of_classifier))
            elif model == "squeezenet":
                self.model = torchvision.models.squeezenet1_1(pretrained=param_pretrained)
                self.model.classifier[1] = torch.nn.Conv2d(self.model.classifier[1].in_features, kind_of_classifier, kernel_size=1)
                self.num_classes = kind_of_classifier
            elif model == "vgg16":
                self.model = torchvision.models.vgg16(pretrained=param_pretrained)
            elif model == "densenet":
                self.model = torchvision.models.densenet161(pretrained=param_pretrained)
            elif model == "inception":
                self.model = torchvision.models.inception_v3(pretrained=param_pretrained)
            elif model == "googlenet":
                self.model = torchvision.models.googlenet(pretrained=param_pretrained)
            elif model == "shufflenet":
                self.model = torchvision.models.shufflenet_v2_x1_0(pretrained=param_pretrained)
            elif model == "mobilenet":
                self.model = torchvision.models.mobilenet_v2(pretrained=param_pretrained)
            elif model == "resnext50_32x4d":
                self.model = torchvision.models.resnext50_32x4d(pretrained=param_pretrained)
            elif model == "resnet34": 
                self.model = torchvision.models.resnet34(pretrained=param_pretrained)
                self.model.fc = torch.nn.Linear(512, kind_of_classifier)
            elif model == "wide_resnet50_2":
                self.model = torchvision.models.wide_resnet50_2(pretrained=param_pretrained)
            elif model == "mnasnet":
                self.model = torchvision.models.mnasnet1_0(pretrained=param_pretrained)
            model_pth = self.getFilePath(name=self.model_name, folder="model")
            self.model.load_state_dict(torch.load(model_pth))
            interval = rospy.get_time() - start_time
            rospy.loginfo("Done with loading modle! Use {:.2f} seconds.".format(interval))
            rospy.loginfo("There are {} objects you want to recognize.".format(kind_of_classifier))
        else:
            rospy.loginfo("Your classifier is wrong. Please check out model struct!")

    def cuda(self,use=False):
        if use == True:
            rospy.loginfo("Using cuda! Need some time to start...")
            self.device = torch.device('cuda')
            start_time = rospy.get_time()
            self.model = self.model.to(self.device)
            interval = rospy.get_time() - start_time
            rospy.loginfo("Done with starting! Can use cuda now! Use {:.2f} seconds to start.".format(interval)) 
        else:
            rospy.loginfo("Do not use cuda!")

    def getFilePath(self,name ,folder="image"):
        rospack = rospkg.RosPack()
        return rospack.get_path(self.package) + "/" + folder + "/" + name  


    def read_param_from_file(self, file_name, file_folder):
        fname = self.getFilePath(name=file_name,folder=file_folder)
        with open(fname, 'r') as in_file:
            try:
                yaml_dict = yaml.load(in_file)
            except yaml.YAMLError as exc:
                print(" YAML syntax  error. File: {}".format(fname))
        return yaml_dict

    def preprocess(self, camera_value): 
        img = camera_value
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.transpose((2, 0, 1))
        img = torch.from_numpy(img).float()
        img = self.process_img_normalize(img)
        img = img.to(self.device)
        img = img[None, ...]
        return img   

    def convert_image_to_cv2(self,img_msg):
        try:
            # Convert your ROS Image ssage to opencv2
            cv2_img = self.bridge.imgmsg_to_cv2(img_msg,desired_encoding="bgr8")
            jpeg_img = bgr8_to_jpeg(cv2_img)
            #self.inference(img=jpeg_img, labels=self.labels)
        except CvBridgeError as e:
            print(e)

    def inference(self, img, labels):
        img_input = img
        img = self.preprocess(img)
        predict = self.model(img)

        # we apply the 'softmax' function to normalize the output vector so it sums to 1 (which makes ti a probability distribution)
        predict = torch.nn.functional.softmax(predict, dim=1)
        print(predict.flatten())
        time.sleep(0.001)

    def on_shutdown(self): 
        rospy.loginfo("{} Close.".format(self.node_name))
        rospy.loginfo("{} shutdown.".format(self.node_name))
        rospy.sleep(1)
        rospy.is_shutdown=True


if __name__ == "__main__" :
    rospy.init_node("inference_model", anonymous=False)
    inference_model_node = Inference_Model_Node()
    rospy.on_shutdown(inference_model_node.on_shutdown)   
    rospy.spin()