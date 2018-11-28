# Copyright 2017-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
import logging
import json
import os
import glob
from io import BytesIO
import requests
import sys

import torch
import torch.nn.functional as F

import fastai
from fastai import *
from fastai.vision import *

# setup the logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# set the constants for the content types
JSON_CONTENT_TYPE = 'application/json'
JPEG_CONTENT_TYPE = 'image/jpeg'

# get the image size from an environment variable for inference
IMG_SIZE = int(os.environ.get('IMAGE_SIZE', '224'))

# Return the Convolutional Neural Network model
def model_fn(model_dir):
    logger.debug('model_fn')
    return torch.jit.load(glob.glob(f'{model_dir}/*_jit'))

# Deserialize the Invoke request body into an object we can perform prediction on
def input_fn(request_body, content_type=JPEG_CONTENT_TYPE):
    logger.info('Deserializing the input data.')
    # process an image uploaded to the endpoint
    if content_type == JPEG_CONTENT_TYPE:
        img = open_image(BytesIO(request_body))
        return _normalize_image(img)
    # process a URL submitted to the endpoint
    if content_type == JSON_CONTENT_TYPE:
        img_request = requests.get(request_body['url'], stream=True)
        img = open_image(BytesIO(img_request.content))
        return _normalize_image(img)        
    raise Exception('Requested unsupported ContentType in content_type: {}'.format(content_type))
    
def _normalize_img(img):
    img_data = img.apply_tfms(crop_pad(), size=224).px
    return normalize(img_data, tensor(imagenet_stats[0]), tensor(imagenet_stats[1])).unsqueeze(0)

# Perform prediction on the deserialized object, with the loaded model
def predict_fn(input_object, model):
    logger.info("Calling model")
    # get the classes from saved 'classes.txt' file
    classes = loadtxt_str('classes.txt')
    
    predict_values = model(input_object)
    preds = F.softmax(predict_values, dim=1)
    conf_score, indx = torch.max(preds, dim=1)
    predict_class = classes[indx]
    print(f'Predicted class is {predict_class}')
    print(f'Predicted values are {predict_values}')
    print(f'Softmax confidence score is {conf_score.item()}')
    response = {}
    response['class'] = predict_class
    response['confidence'] = conf_score.item()
    return response

# Serialize the prediction result into the desired response content type
def output_fn(prediction, accept=JSON_CONTENT_TYPE):        
    logger.info('Serializing the generated output.')
    if accept == JSON_CONTENT_TYPE:
        return json.dumps(prediction), accept
    raise Exception('Requested unsupported ContentType in Accept: {}'.format(accept))    

