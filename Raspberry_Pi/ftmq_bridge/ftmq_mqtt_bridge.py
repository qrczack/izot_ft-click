"""
FTMQ to MQTT bridge.
Connects a FTMQ based network to an MQTT broker.
Published messages in the FTMQ network are publised to the MQTT broker.
Received messages from the MQTT broker are sent to the FTMQ network.
A topic lookup table mapping MQTT topics to FTMQ identifier is needed, in yaml format.


Usage:     ftmq_mqtt_bridge.py [--broker <broker>] <FTMQ_port> <baud_rate> <lookup>
           ftmq_mqtt_bridge.py (-h | --help)

Arguments:
    <FTMQ_port>              serial port to connect to FTMQ device
    <baud_rate>             serial port baud_rate
    <lookup>                file containing the topics lookup table

Options:
    -h --help               Show this screen
    --broker <broker>       Hostname of IP address of the MQTT broker [default: 127.0.0.1]
"""

from docopt import docopt

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish

import serial

import time

import yaml
import json
import struct

import sys

POLL_WAIT_TIME = 0.5    # sleep time between serial polls. Avoids CPU usage on active waiting
FTMQ_PKT_LEN = 5         # id + 4 byte data
HEADER_CHAR = 0x40

class FTMQ_MQTT_Bridge :

    def __init__(self, broker, FTMQ_port, baud_rate, topics_lookup) :
        self.broker = broker
        self.FTMQ_port = FTMQ_port
        self.baud_rate = baud_rate
        self.topics_lookup = topics_lookup
        self.read_buffer = bytearray()
        self.waiting_header = 0

    def on_connect(self, client, userdata, flags, rc):
        print("Connected with result code "+str(rc))
        for topic in self.topics_lookup['mqtt_subscriptions']:
            self.client.subscribe(topic)

    def on_message(self, client, userdata, msg):
        print('on msg ' +msg.topic+" "+str(msg.payload))
        # publish to FTMQ
        for t in self.topics_lookup['lookup_table'].items():
            if t[0] == msg.topic:
                id = bytes([t[1]['id']])
                try:
                    value = json.loads(msg.payload.decode('utf-8'))[t[1]['name']]
                    if t[1]['type'] == 'int32':
                        data = struct.pack('<i', value)
                    elif t[1]['type'] == 'float':
                        data = struct.pack('<f', value)
                    elif t[1]['type'] == 'array':
                        data = bytearray(4)
                        data[0] = value[0]
                        data[1] = value[1]
                        data[2] = value[2]
                        data[3] = value[3]
                    self.serial.write([HEADER_CHAR])
                    self.serial.write([HEADER_CHAR])
                    self.serial.write(id)
                    self.serial.write(data)
                except:
                    print("Unexpected error:", sys.exc_info()[0])
                return

    def start_FTMQ(self):
        data = struct.pack('<i', 0)
        self.serial.write([HEADER_CHAR])
        self.serial.write([HEADER_CHAR])
        self.serial.write(b'\x00')
        self.serial.write(data)

    def poll_FTMQ(self):
        # parse all available data in the serial buffer
        data = self.serial.read(self.serial.in_waiting)
        for byte in data:
            self.parse_FTMQ(byte)

    def parse_FTMQ(self, byte):
        if self.waiting_header < 2:
            if byte == HEADER_CHAR:
                self.waiting_header += 1
        else:
            self.read_buffer.append(byte)
            if len(self.read_buffer) == FTMQ_PKT_LEN:
                print("receiving serial: ", self.read_buffer)
                id = self.read_buffer[0]
                value = self.read_buffer[1:]
                for t in self.topics_lookup['lookup_table'].items():
                    if t[1]['id'] == id:
                        if t[1]['type'] == 'int32':
                            [data] = struct.unpack('<i', value)
                        elif t[1]['type'] == 'float':
                            [data] = struct.unpack('<f', value)
                        elif t[1]['type'] == 'array':
                            data = bytearray(4)
                            data[0] = value[0]
                            data[1] = value[1]
                            data[2] = value[2]
                            data[3] = value[3]
                            data = list(data)
                        data = {t[1]['name'] : data}
                        #print(type(data), data)
                        self.client.publish(t[0], json.dumps(data))
                self.read_buffer = bytearray() # cleanup
                self.waiting_header = 0

    def run(self) :
        # connect to FTMQ dev
        self.serial = serial.Serial(self.FTMQ_port, self.baud_rate, timeout=POLL_WAIT_TIME)
        self.start_FTMQ()
        # MQTT client
        self.client = mqtt.Client()
        # setup callbacks
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        # connect to MQTT broker
        self.client.connect(self.broker)

        # comunications loop
        self.client.loop_start()

        run_loop = True
        while run_loop:
            self.poll_FTMQ()
            time.sleep(POLL_WAIT_TIME)

        self.client.loop_stop()




def main():
    args = docopt(__doc__)
    print(args)
    # parse topics lookup file
    with open(args['<lookup>'], 'r') as stream:
        try:
            topics_lookup = yaml.safe_load(stream)
            print(topics_lookup)
        except yaml.YAMLError as exc:
            print(exc)
        else:
            app = FTMQ_MQTT_Bridge(args['--broker'], args['<FTMQ_port>'], args['<baud_rate>'], topics_lookup)
            app.run()

if __name__ == "__main__":
    main()
