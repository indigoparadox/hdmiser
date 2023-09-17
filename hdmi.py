#!/usr/bin/env python3

import serial
import argparse
from configparser import ConfigParser

# TODO: Add MQTT daemon support.

def ser_write_read( ser_path, out_bytes ):

    with serial.Serial( ser_path, 9600, rtscts=False, dsrdtr=False, xonxoff=True, stopbits=serial.STOPBITS_ONE, timeout=3 ) as ser:
        ser.write( out_bytes )
        ser_line = b''
        while True:
            c = ser.read()
            if b'' == c:
                break
            elif b'\n' == c:
                print( ser_line )
                ser_line = b''
            elif b'\r' != c:
                ser_line += c

def set_out( ser_path, out_idx, in_idx ):

    ser_write_read( \
        ser_path, 'OUT0{}:0{}.'.format( in_idx, out_idx ).encode( 'utf-8' ) )

def status( ser_path ):

    ser_write_read( ser_path, b'STA.' )

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument( '-c', '--config', default='hdmi.ini' )

    parser.add_argument( 'profile' )

    args = parser.parse_args()

    config = ConfigParser()
    config.read( args.config )

    for pair in config['profiles'][args.profile].split( ',' ):
        pair_arr = pair.split( ':' )
        set_out( config['global']['serial_port'], pair_arr[0], pair_arr[1] )

    #set_out( args.serial, 4, 7 )
    #set_out( args.serial, 8, 1 )
    #set_out( args.serial, 7, 7 )
    #set_out( args.serial, 7, 1 )

if '__main__' == __name__:
    main()

