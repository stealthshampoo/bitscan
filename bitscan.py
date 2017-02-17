import os
import sys
import pickle
import signal
from twitchbot import TwitchBot

def bit_to_string(bit_amount, label):
    if label is False:
        bitf = str(bit_amount)
    else:
        if bit_amount == 1:
            bitf = str(bit_amount) + ' Bit'
        else:
            bitf = str(bit_amount) + ' Bits'
    return bitf

def load_bit_info():
    try:
        with open('bit.data', 'rb') as f:
            bit_info = pickle.load(f)
    except IOError:
        bit_info = {
            'latest': { 'user': '', 'amount': 0 },
            'max': { 'user': '', 'amount': 0}
        }

    return bit_info

def save_bit_info(bit_info):
    with open('bit.data', 'wb') as f:
        pickle.dump(bit_info, f)

def read_bit_config(filename):
    config = {'max_user_len': '25',
              'amount_only': 'false',
              'equal_max_override': 'true',
              'format': '$latest $latestamount $max $maxamount'
              }
    try:
        with open(filename, 'r') as f:
            flist = f.read().split('\n')
    except IOError as e:
        print("Error: %s." % e)
        sys.exit(1)

    for line in flist:
        tokens = line.partition('=')
        if len(tokens) == 3 and not line.startswith('#'):
            name = tokens[0].strip()
            value = tokens[2].strip()
            config[name] = value

    return config

def write_bit_config(filename, config, bit_info):
    include_label = config['amount_only'].lower() == 'false'

    latest_amount = bit_to_string(bit_info['latest']['amount'], include_label)
    max_amount = bit_to_string(bit_info['max']['amount'], include_label)

    cutoff = int(config['max_user_len'])

    display = config['format'].replace('\\n', '\n')
    display = display.replace('$latest', bit_info['latest']['user'][0:cutoff])
    display = display.replace('$max', bit_info['max']['user'][0:cutoff])
    display = display.replace('$lamount', latest_amount)
    display = display.replace('$mamount', max_amount)

    try:
        with open(filename, 'w') as f:
            f.write(display)
    except IOError as i:
        print("Error: Writing to file: %s." % i)

def scan(bot, state):
    bit_info = load_bit_info()
    config = read_bit_config('bitconfig.txt')

    def exit_scan():
        save_bit_info(bit_info)
        print('\nExiting program.')
        state.ack = True
        sys.exit(0)

    def signal_exit(signal, frame):
        exit_scan()
     
    while state.on:
        text = bot.incoming()
        
        if text.tag.isCheer:
            amount = text.tag.bits
            username = text.tag.display_name

            if username.strip() == '':
                username = text.username

            bit_info['latest']['user'] = username
            bit_info['latest']['amount'] = amount

            if config['equal_max_override'].lower() == 'true':
                if amount >= bit_info['max']['amount']:
                    bit_info['max']['user'] = username
                    bit_info['max']['amount'] = amount
            else:
                if amount > bit_info['max']['amount']:
                    bit_info['max']['user'] = username
                    bit_info['max']['amount'] = amount
                        
            write_bit_config('display.txt', config, bit_info)

    exit_scan()
