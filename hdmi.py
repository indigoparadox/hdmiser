#!/usr/bin/env python3

import serial
import argparse
import logging
import re
import time
from configparser import ConfigParser
from paho.mqtt import client as mqtt_client
import ssl

PATTERN_OUTPUT = re.compile( r'Output (?P<out>[0-9]+) Switch To In (?P<in>[0-9]+)!' )

class HDMISerial:

    def __init__( self, serial_path : str, timeout=3, serial_speed=9600 ):
        logger = logging.getLogger( 'serial' )
        logger.info( 'serial port connected!' )
        self.mqtt = None
        self.topic = None
        self.busy = False
        self.serial = serial.Serial(
            serial_path,
            serial_speed,
            rtscts=False,
            dsrdtr=False,
            xonxoff=True,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout )

    def __enter__( self ):
        return self

    def __exit__( self, exc_type, exc_value, exc_tb ):
        logger = logging.getLogger( 'serial' )
        self.serial.close()
        logger.info( 'serial port closed!' )

    def lock( self ):
        logger = logging.getLogger( 'serial.lock' )
        while self.busy:
            logger.debug( 'waiting for serial port...' )
            time.sleep( 1 )
        logger.debug( 'locking serial port...' )
        self.busy = True

    def unlock( self ):
        logger = logging.getLogger( 'serial.lock' )
        logger.debug( 'unlocking serial port...' )
        self.busy = False

    def write( self, out : str ):
        logger = logging.getLogger( 'serial.write' )
        logger.debug( out )
        self.serial.write( out.encode( 'utf-8' ) )

    def read( self ):
        logger = logging.getLogger( 'serial.read' )
        ser_line = b''
        while True:
            c = self.serial.read()
            if b'' == c:
                break
            elif b'\n' == c:
                logger.debug( ser_line )
                yield ser_line.decode( 'utf-8' )
                ser_line = b''
            elif b'\r' != c:
                ser_line += c

    def l_set_out( self, out_str, in_str ):
        self.lock()
        self.write( 'OUT0{}:0{}.'.format( int( out_str ), int( in_str ) ) )
        for line in self.read():
            match = PATTERN_OUTPUT.match( line )
            if match and self.mqtt:
                # TODO: Verify that switch was successful.
                pass
                #self.publish( match.group( 'out' ), match.group( 'in' ) )
        self.unlock()

    def l_status( self ):
        self.lock()
        self.write( 'STA.' )
        for line in self.read():
            match = PATTERN_OUTPUT.match( line )
            if match:
                self.publish( match.group( 'out' ), match.group( 'in' ) )
        self.unlock()

    def publish( self, out_str, in_str ):    
        if self.mqtt:
            self.mqtt.publish( '{}/{}'.format(
                self.topic, int( out_str ) ), int( in_str ), retain=True )

def on_mqtt_connected( client, userdata, flags, rc ):
    logger = logging.getLogger( 'mqtt' )
    logger.info( 'MQTT connected!' )
    client.subscribe( '{}/#'.format( userdata['topic'] ) )

def on_mqtt_publish( client, userdata, mid ):
    logger = logging.getLogger( 'mqtt.publish' )
    logger.debug( mid )

def on_mqtt_message( client, userdata, message ):
    logger = logging.getLogger( 'mqtt.message' )

    # Grab the output from the topic and the input from the payload.
    topic_arr = message.topic.split( '/' )
    out_str = topic_arr[-2]
    in_str = message.payload.decode( 'utf-8' )

    if 'set' == topic_arr[-1] and \
    0 <= int( out_str ) and 8 >= int( out_str ) and \
    0 <= int( in_str ) and 8 >= int( in_str ):
        logger.debug( '{} = {}'.format( out_str, in_str ) )
        userdata['serial'].l_set_out( out_str, in_str )

def connect_mqtt( ser : HDMISerial, host : str, port: int, topic : str, username : str, password : str, uid : str, use_ssl=False, ssl_ca=None ) -> mqtt_client.Client:
    logger = logging.getLogger( 'mqtt' )
    mqtt = mqtt_client.Client( uid, True, None, mqtt_client.MQTTv31 )
    if use_ssl:
        mqtt.tls_set( ssl_ca, tls_version=ssl.PROTOCOL_TLSv1_2 )
    mqtt.username_pw_set( username, password )
    mqtt.on_connect = on_mqtt_connected
    mqtt.on_message = on_mqtt_message
    mqtt.on_publish = on_mqtt_publish
    mqtt.user_data_set( {'topic': topic, 'serial': ser} )
    logger.info( 'connecting to MQTT at {}:{}...'.format( host, port ) )
    mqtt.connect( host, port )
    return mqtt

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument( '-c', '--config', default='hdmi.ini' )

    parser.add_argument( '-v', '--verbose', action='store_true' )

    parser.add_argument( '-m', '--mqtt', action='store_true' )

    group = parser.add_mutually_exclusive_group( required=True )

    group.add_argument( '-p', '--profile', action='store' )

    group.add_argument( '-s', '--status', action='store_true' )

    group.add_argument( '-b', '--bridge', action='store_true' )

    args = parser.parse_args()

    config = ConfigParser()
    config.read( args.config )

    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    logging.basicConfig( level=level )
    logger = logging.getLogger( 'main' )

    with HDMISerial( config['global']['serial_port'] ) as ser:

        # Connect to MQTT if required.
        if args.mqtt:
            mqtt = connect_mqtt(
                ser,
                config['mqtt']['host'],
                config['mqtt'].getint( 'port', fallback=1883 ),
                config['mqtt']['topic'],
                config['mqtt']['username'],
                config['mqtt']['password'],
                config['mqtt']['uid'],
                config['mqtt'].getboolean( 'ssl', fallback=False ),
                config['mqtt']['ca'] )
            ser.mqtt = mqtt
            ser.topic = config['mqtt']['topic']
            mqtt.loop_start()
    
        # Execute requested action.

        if args.profile:
            for pair in config['profiles'][args.profile].split( ',' ):
                pair_arr = pair.split( ':' )
                ser.l_set_out( pair_arr[1], pair_arr[0] )

        elif args.status:
            ser.status()

        elif args.bridge:
            ser.l_status()
            while True:
                ser.lock()
                for line in ser.read():
                    match = PATTERN_OUTPUT.match( line )
                    if match and mqtt:
                        ser.publish( match.group( 'out' ), match.group( 'in' ) )
                ser.unlock()
                time.sleep( 1 )

if '__main__' == __name__:
    main()

