#
# encoding = utf-8
#
import os.path
import base64
import socket
import sys
import argparse
import logging
from logging import Logger
from typing import Dict

import socks
from requests import Session
from requests.auth import HTTPProxyAuth, HTTPDigestAuth
from datetime import datetime, timedelta, timezone
import dateutil.parser
import math
import configparser
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ISO_URL_INFO = {'WEB': {'URL': 'https://proofpointisolation.com/api/v2/reporting/usage-data'},
                'URL': {'URL': 'https://urlisolation.com/api/v2/reporting/usage-data'}}


def encrypt(profile_name: str, text: str) -> str:
    ad = profile_name.encode('utf-8')
    data = text.encode('utf-8')
    key = AESGCM.generate_key(bit_length=128)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    enc = aesgcm.encrypt(nonce, data, ad)
    secret = base64.b64encode(nonce + key + enc)
    return secret.decode('utf-8')


def decrypt(profile_name: str, data: str) -> str:
    ad = profile_name.encode('utf-8')
    secret = base64.b64decode(data.encode('utf-8'))
    nonce = secret[:12]
    key = secret[12:12 + 16]
    enc = secret[12 + 16:]
    aesgcm = AESGCM(key)
    data = aesgcm.decrypt(nonce, enc, ad)
    return data.decode('utf-8')


def get_script_path() -> str:
    return os.path.abspath(os.path.dirname(__file__))


def list_config_profiles():
    config = configparser.ConfigParser()
    config.read(os.path.join(get_script_path(), 'iso2web.ini'))
    if not config.sections():
        print("No profiles defined")

    for section in config.sections():
        print("\nProfile ID: {}".format(section))
        for k, v in config[section].items():
            print("{}: {}".format(k,v))


def save_config_profile(profile_name: str, options: Dict):
    config = configparser.ConfigParser()
    config.read(os.path.join(get_script_path(), 'iso2web.ini'))
    config[profile_name] = options
    with open(os.path.join(get_script_path(), 'iso2web.ini'), "w") as config_file:
        config.write(config_file)


def delete_config_profile(profile_name: str):
    config = configparser.ConfigParser()
    config.read(os.path.join(get_script_path(), 'iso2web.ini'))
    if config.has_section(profile_name):
        config.remove_section(profile_name)
        print("Profile deleted: {}".format(profile_name))
        with open(os.path.join(get_script_path(), 'iso2web.ini'), "w") as config_file:
            config.write(config_file)
    else:
        print("No profile defined: {}".format(profile_name))


def get_script_version() -> str:
    return '0.1.0'


def get_app_name() -> str:
    return 'isolation_to_webhook'


def get_check_point(file: str) -> str:
    if os.path.isfile(file):
        with open(file, 'r') as check_point_file:
            return check_point_file.read()
    return None


def save_check_point(file: str, value: str):
    with open(file, 'w') as check_point_file:
        check_point_file.write(value)


# Get data chunk for event submission
def make_chunks(data, length):
    for i in range(0, len(data), length):
        yield data[i:i + length]


def collect_events(log: Logger, options: Dict):
    # Current log level
    loglevel = logging.getLevelName(log.getEffectiveLevel())
    log.info("Log Level: {}".format(loglevel))

    # Get App Name
    app_name = get_app_name()
    log.info("Application Name: {}".format(app_name))

    # Get the application version
    app_version = get_script_version()
    log.info("Script Version: {}".format(app_version))

    # Get Endpoint Type
    input_type = options.get('input_type')
    log.info("Input Type: {}".format(input_type))

    # User defined input stanza
    identifier = options.get('identifier')
    log.info("Unique Identifier: {}".format(identifier))

    # Checkpoint key for next start date
    checkpoint_file = "{}.checkpoint".format(identifier)
    log.debug("Checkpoint File: {}".format(checkpoint_file))

    # Get checkpoint date value
    checkpoint_data = get_check_point(checkpoint_file)
    log.info("Checkpoint Data: {}".format(checkpoint_data))

    # Get API key
    api_key = options.get('api_key')
    # Logging of API key even in Debug
    log.debug("API Key: {}".format(api_key))

    # Get Page Size
    page_size = options.get('page_size')
    log.debug("Page Size: {}".format(page_size))

    # Get Page Size
    chunk_size = options.get('chunk_size')
    log.debug("Chunk Size: {}".format(chunk_size))

    # Check request timeout
    timeout = float(options.get('timeout'))
    log.debug("HTTP Request Timeout: {}".format(timeout))

    # Callback URL
    callback = options.get('callback')
    log.debug("Callback URL: {}".format(callback))

    # API URL
    url = ISO_URL_INFO[input_type]['URL']
    log.debug("Base URL: {}".format(url))

    proxies = None
    credentials = ''

    if 'proxy_user' in options and 'proxy_pass' in options:
        credentials = "{}:{}@".format(options['proxy_user'], options['proxy_pass'])

    if options['proxy_type']:
        proxies = {'https': "{}://{}{}:{}".format(options['proxy_type'], credentials, options['proxy_host'],
                                                  options['proxy_port'])}

    # Will be set to start date by either checkpoint or 30days back
    date_start = None

    # Will be set to current date
    date_end = None

    # If not previously excuted
    if checkpoint_data is None:
        current_date = datetime.now(timezone.utc)
        date_end = current_date.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
        date_start = (current_date - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
    else:
        date_end = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
        # Incremental pull from last oldest dataset
        date_start = checkpoint_data

    # Log the current end of the range
    log.info("Start Date: {}".format(date_start))

    # Log the current end of the range
    log.info("End Date: {}".format(date_end))

    # Authentication via Header (AppInspect Fix)
    headers = {'Authorization': 'Bearer {}'.format(api_key)}

    parameters = {"from": date_start, "to": date_end, "pageSize": page_size}

    isolation_data = []

    # Current page
    page = 1

    # Assume at least 1 page
    pages = 1

    # Records processed
    records = 0

    # Used store the most recent date in the dataset processed
    most_recent_datetime = None

    session = Session()

    # Start assuming we have one page but total pages are calculated in the loop
    while True:
        response = None
        try:
            response = session.get(url, proxies=proxies, params=parameters, headers=headers,
                                   cookies=None, verify=True, cert=None, timeout=timeout)
        except Exception as e:
            log.error("Call to send_http_request failed: {}".format(e))
            break

        if response.status_code == 200:
            log.debug("Proofpoint Isolation API successfully queried")
        elif response.status_code == 400:
            log.error("Proofpoint Isolation API bad request")
        elif response.status_code == 403 or response.status_code == 401:
            log.error("Proofpoint Isolation API api key invalid")
        else:
            log.error("Proofpoint Isolation API unknown failure [{}]".format(response.status_code))

        # Raise HTTPError exception if we had a failure
        if response.status_code != 200:
            response.raise_for_status()

        r_json = response.json()

        # Since we need the jobID for subsequent requests add it to the request
        # parameters for the next call to the web service.
        if 'jobId' in r_json:
            parameters['jobId'] = r_json['jobId']
            # Log the current jobID
            log.debug("Job ID: {}".format(r_json['jobId']))
        else:
            log.error("Job ID is not defined in the JSON response, exiting")
            break

        # Since we need the pageToken for subsequent requests add it to the
        # request parameters for the next call to the web service.
        if 'pageToken' in r_json:
            parameters['pageToken'] = r_json['pageToken']
            # Log the current pageToken
            log.debug("Page Token: {}".format(r_json['pageToken']))
        else:
            log.debug("Page Token: None")

        # We will only have data once the status is COMPLETED so we poll until
        # our request state is COMPLETED.
        if 'status' in r_json:
            log.debug("Status: {}".format(r_json['status']))
            # According to the API we keep polling with the jobId until
            # the the status is completed.
            if r_json['status'].casefold() != "COMPLETED".casefold():
                log.debug("Polling until status is COMPLETED.")
                continue
        else:
            log.error("Status is not defined in the JSON response, exiting")
            break

        # Total is not a realiable way to determine the number of record pages to read for
        # we really need to read until status == COMPLETED and pageToken == None
        # could be useful information at some point in the future
        if 'total' in r_json:
            log.debug("Total Records: {}".format(r_json['total']))
            pages = math.ceil(int(r_json['total']) / int(page_size))
        else:
            log.debug("Total Records: None")

        # Data contains the total number or records for the current query
        if 'data' in r_json:
            log.info("Data Records: {}".format(len(r_json['data'])))
            if len(r_json['data']) > 0:
                log.info("Page: {} of {}".format(page, pages))
                for entry in r_json['data']:
                    # Collect all data for the current time range
                    isolation_data.append(entry)
            page += 1
        else:
            log.info("Data Records: None")

        # Terminal case for the while loop
        if r_json['status'].casefold() == "COMPLETED".casefold() and 'pageToken' not in r_json:
            break

    if isolation_data:
        # Sort the isolation data by oldest to newest date
        isolation_data_sorted = sorted(isolation_data, key=lambda x: dateutil.parser.parse(x['date']))
        for chunk in make_chunks(isolation_data_sorted, chunk_size):
            # Get last date for the chunk we are processing
            last_processed_entry_date = dateutil.parser.parse(chunk[-1]['date'])
            # Write the single event
            try:
                response = session.post(callback, json=chunk, headers=None, cookies=None,
                                        verify=True, cert=None,
                                        timeout=timeout)
                records += len(chunk)
                next_start_date = last_processed_entry_date + timedelta(seconds=1)
                save_check_point(checkpoint_file, next_start_date.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3])
                log.info("Updating checkpoint [{}] with: {}".format(checkpoint_file, next_start_date.strftime(
                    '%Y-%m-%dT%H:%M:%S.%f')[:-3]))
            except Exception as e:
                log.error("Failed to post data to callback: {}".format(e))
                break

    log.info("Total records processed: {}".format(records))


def main():
    # if len(sys.argv) == 1:
    #     print('iso2web [-h] --endpoint [web|url] ')
    #     exit(1)

    parser = argparse.ArgumentParser(prog="iso2web",
                                     description="""Tool to send Proofpoint Isolation data to LogRythm""",
                                     formatter_class=lambda prog: argparse.HelpFormatter(prog, max_help_position=80))

    sub = parser.add_subparsers(title='Required Actions',
                                description='',
                                required=True,
                                help='An action must be specified',
                                dest='action')

    parser_list = sub.add_parser('list')

    parser_delete = sub.add_parser('delete')
    parser_delete.add_argument('-i', '--identifier', metavar='<unique_id>', dest="identifier", type=str, required=True,
                               help='Unique identifier associated with the import.')

    parser_run = sub.add_parser('run')
    parser_run.add_argument('-i', '--identifier', metavar='<unique_id>', dest="identifier", type=str, required=True,
                            help='Unique identifier associated with the import.')

    parser_add = sub.add_parser('add')
    parser_add.add_argument('-i', '--identifier', metavar='<unique_id>', dest="identifier", type=str, required=True,
                            help='Unique identifier associated with the import.')
    parser_add.add_argument('-e', '--endpoint', metavar='<web|url>', choices=['WEB', 'URL'], dest="endpoint",
                            type=str.upper, required=True, help='Isolation API endpoint')
    parser_add.add_argument('-k', '--apikey', metavar='<level>',
                            dest="api_key", type=str, required=True,
                            help='Proofpoint Isolation API Key.')
    parser_add.add_argument('-t', '--target', metavar='<url>', dest="callback", type=str, required=True,
                            help='Target URL to post the JSON events.')
    parser_add.add_argument('-l', '--loglevel', metavar='<level>',
                            choices=['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'],
                            dest="log_level", type=str.upper, required=False,
                            help='Log level to be used critical, error, warning, info or debug.')
    parser_add.add_argument('-c', '--chunk', metavar='<chunk_size>',
                            dest="chunk_size", type=int, required=False, default=10000, choices=range(1, 10001),
                            help='Number of records processed per event 1 to 10000 (default: 10000)')
    parser_add.add_argument('--pagesize', metavar='<page_size>',
                            dest="page_size", type=int, required=False, default=10000, choices=range(1, 10001),
                            help='Number of records processed per request 1 to 10000 (default: 10000).')
    parser_add.add_argument('--timeout', metavar='<timeout>',
                            dest="timeout", type=int, required=False, default=60, choices=range(1, 3601),
                            help="Number of seconds before the web request timeout occurs 1 to 3600 (default: 60)")

    parser_add.add_argument('--proxy', metavar='<none|http|socks4|socks5>',
                            choices=['none', 'http', 'socks4', 'socks5'],
                            default='none', dest="proxy_type", type=str.lower, required=False, help='Proxy type')
    parser_add.add_argument('--proxy-host', metavar='<host>', dest="proxy_host",
                            type=str, required=False, help='Proxy hostname')
    parser_add.add_argument('--proxy-port', metavar='<port>', dest="proxy_port",
                            type=int, required=False, help='Proxy port')
    parser_add.add_argument('--proxy-user', metavar='<username>', dest="proxy_user",
                            type=str, required=False, help='Proxy username')
    parser_add.add_argument('--proxy-pass', metavar='<password>', dest="proxy_pass",
                            type=str, required=False, help='Proxy password')

    args = parser.parse_args()
    options = dict()

    if args.action == 'list':
        list_config_profiles()
    elif args.action == 'add':
        options['log_level'] = args.log_level
        options['input_type'] = args.endpoint
        options['callback'] = args.callback
        options['chunk_size'] = args.chunk_size
        options['page_size'] = args.page_size
        options['timeout'] = args.timeout
        options['api_key'] = encrypt(args.identifier, args.api_key)

        if args.proxy_type != 'none' and (not args.proxy_host or not args.proxy_port):
            parser.error('--proxy must be used with --proxy-host and --proxy-port')
        else:
            options['proxy_type'] = args.proxy_type
            options['proxy_host'] = args.proxy_host
            options['proxy_port'] = args.proxy_port
            if (args.proxy_user and not args.proxy_pass) or (not args.proxy_user and args.proxy_pass):
                parser.error('--proxy-user and --proxy-pass must both be used')
            elif args.proxy_user and args.proxy_pass:
                options['proxy_user'] = args.proxy_user
                options['proxy_pass'] = encrypt(args.identifier, args.proxy_pass)

        save_config_profile(args.identifier, options)
    elif args.action == 'delete':
        delete_config_profile(args.identifier)
    elif args.action == 'run':
        config = configparser.ConfigParser()
        config.read(os.path.join(get_script_path(), 'iso2web.ini'))
        if not config.has_section(args.identifier):
            print("No profile defined: {}".format(args.identifier))

        section = config[args.identifier]
        options['identifier'] = args.identifier
        options['log_level'] = section.get('log_level')
        options['input_type'] = section.get('input_type')
        options['callback'] = section.get('callback')
        options['chunk_size'] = section.getint('chunk_size')
        options['page_size'] = section.getint('page_size')
        options['timeout'] = section.getint('timeout')
        options['api_key'] = decrypt(args.identifier, section.get('api_key'))

        if section.get('proxy_type') != 'none' and section.get('proxy_host') and section.get('proxy_port'):
            options['proxy_type'] = section.get('proxy_type')
            options['proxy_host'] = section.get('proxy_host')
            options['proxy_port'] = section.getint('proxy_port')
            if section.get('proxy_user') and section.get('proxy_pass'):
                options['proxy_user'] = section.get('proxy_user')
                options['proxy_pass'] = decrypt(args.identifier, section.get('proxy_pass'))

        log = logging.getLogger('iso2web')
        log.setLevel(options['log_level'])

        stdout_handler = logging.StreamHandler(stream=sys.stdout)
        stdout_fmt = logging.Formatter('%(message)s')
        stdout_handler.setFormatter(stdout_fmt)

        file_handler = logging.FileHandler("{}.log".format(args.identifier))
        file_fmt = logging.Formatter(
            '%(asctime)s %(levelname)s pid=%(process)d tid=%(threadName)s file=%(filename)s:%(funcName)s:%(lineno)d %(name)s | %(message)s',
            "%Y-%m-%dT%H:%M:%S%z")

        file_handler.setFormatter(file_fmt)

        log.addHandler(stdout_handler)
        log.addHandler(file_handler)

        collect_events(log, options)


# Main entry point of program
if __name__ == '__main__':
    main()
