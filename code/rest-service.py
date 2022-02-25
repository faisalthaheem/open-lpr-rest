"""
   Copyright 2019 Faisal Thaheem

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""
    
from amqp import ThreadedAmqp

import argparse
import time
import pprint
import uuid
import sys
import os
import logging
import yaml
import shutil
import json
import redis

from pymongo import MongoClient

from flask import Flask, request
from werkzeug.utils import secure_filename
app = Flask(__name__)


#create logger
logger = logging.getLogger('rest.service')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('rest.service.log')
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
# create formatter and add it to the handlers
formatter = logging.Formatter('[%(levelname)1.1s %(asctime)s] %(message)s',"%Y-%m-%d %H:%M:%S")
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

ap = argparse.ArgumentParser()
ap.add_argument("-cf", "--config.file", default='rest.service.yaml',
        help="Config file describing service parameters")
args = vars(ap.parse_args())


## mq related
broker = None

#app config
config = None
	
@app.route('/process', methods = ['GET', 'POST'])
def upload_file():
   if request.method == 'POST':
      
      
      try:

         f = request.files['image']

         secure_upload_path = os.path.join(config['storage']['upload-path'],secure_filename(f.filename))
         f.save(secure_upload_path)

         msg = {}
         msg['_id'] = str(uuid.uuid4())
         msg['filename'] = secure_filename(f.filename)
         msg['creationtime'] = time.time()

         # save to disk
         try:
            unique_name = "{}_{}".format(msg['_id'], msg['filename'])
            msg['unique_name'] = unique_name
            destPath = os.path.join(storagePath, unique_name)
            logger.info("Moving from [{}] to [{}]".format(secure_upload_path, destPath))
            
            shutil.move(secure_upload_path, destPath)

         except:
            logger.error("An error occurred: ", exc_info=True)
         
         r = redis.Redis(config['redis']['host'], port=config['redis']['port'])


         client = MongoClient(config['mongo']['uri'])

         #open db
         if not "openlpr" in client.list_database_names():
            logger.info("database openlpr does not exist, will be created after first document insert")
         
         db = client["openlpr"]

         # save to db
         dbcollection = db["lprevents"]
         dbcollection.insert_one(msg)
         
   
         #post to mq
         publisher.publish_message(msg)
         logger.info("[{}] published".format(msg['_id']))
         
         time.sleep(config['redis']['get_timeout'])
         
         res = {
            "msg":"Timeout processing request"
         }
         
         if r.exists(msg['_id']):
            res = r.getdel(msg['_id'])
            res = json.loads(res)
            
         print("Got reply [{}]".format(res)) 
           
         r.close()
         
      except:
            logger.error("upload_file | An error occurred: ", exc_info=True)
      
      return res


def ocrResultReceived(msg):

   try:
      # load image
      decoded = json.loads(msg)
      logger.debug("ocrResultReceived ---> {}".format(decoded))
      
      r = redis.Redis(config['redis']['host'], port=config['redis']['port'])
      r.set(decoded['_id'], msg)
      r.close()
       
   except:
      logger.error("ocrResultReceived | An error occurred: ", exc_info=True)

if __name__ == '__main__':
   
   try:

      with open(args["config.file"]) as stream:
         try:
               if os.getenv('PRODUCTION') is not None: 
                     config = yaml.safe_load(stream)['prod']
               else:
                     config = yaml.safe_load(stream)['dev']

               pprint.pprint(config)
               
         except yaml.YAMLError as err:
               logger.error("An error occurred: ", exc_info=True)
               sys.exit(-1)

      storagePath = config['storage']['path']
      logger.info("Will be storing all files to [{}]".format(storagePath))

   
      
      logger.info("Connecting publisher")
      
      brokerUrl = config['broker']['uri']
      logger.info("Using broker url [{}]".format(brokerUrl))

      publisher = ThreadedAmqp()
      publisher.init(
            brokerUrl,
            consumerMode=False,
            exchange=config['broker']['publishTo']['exchange'],
            exchangeType=config['broker']['publishTo']['exchangeType'],
            routingKey=config['broker']['publishTo']['routingKey'],
      )
      publisher.start()
      
      consumer = ThreadedAmqp()
      consumer.init(
            brokerUrl,
            consumerMode=True,
            exchange=config['broker']['consumeFrom']['exchange'],
            exchangeType=config['broker']['consumeFrom']['exchangeType'],
            routingKey=config['broker']['consumeFrom']['routingKey'],
            queueName=config['broker']['consumeFrom']['queueName'],
      )
      consumer.callbackEvents.on_message += ocrResultReceived
      consumer.start()

      if os.getenv('PRODUCTION') is not None: 
         app.run(host='0.0.0.0')
      else:     
         app.run(debug = True)
      
   except:
      logger.error("An error occurred: ", exc_info=True)
